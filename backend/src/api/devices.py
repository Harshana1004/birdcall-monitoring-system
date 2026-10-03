import asyncio
import math
import uuid
from datetime import (
    datetime,
    timezone,
)
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
    status,
)
from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.exc import (
    IntegrityError,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.api.access import (
    device_visibility,
    get_visible_device,
)
from src.api.auth import (
    AdminUser,
    CurrentUser,
)
from src.api.schemas import (
    ClaimCodeResponse,
    DeviceClaimRequest,
    DeviceCreate,
    DeviceCreatedResponse,
    DeviceOwnerAssignment,
    DeviceOwnerSummary,
    DeviceResponse,
    DeviceSummaryResponse,
    DeviceUpdate,
    ErrorResponse,
    PaginatedResponse,
    PaginationMetadata,
    TimelineRecording,
)
from src.core.config import settings
from src.core.exceptions import (
    DeviceAlreadyClaimedError,
    DeviceNotFoundError,
    DuplicateDeviceCodeError,
    InvalidDeviceClaimError,
    PermissionDeniedError,
    UserNotFoundError,
)
from src.core.security import (
    generate_claim_code,
    hash_secret,
    normalize_claim_code,
    verify_secret,
)
from src.database import get_db
from src.models import (
    Detection,
    Device,
    Recording,
    User,
)
from src.services import activity


router = APIRouter(
    prefix="/api/v1/devices",
    tags=["Devices"],
)


DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db),
]

# Fields a device owner may edit; everything else is admin-only.
OWNER_EDITABLE_FIELDS = {
    "name",
    "description",
    "latitude",
    "longitude",
    "installed_at",
}


# ============================================================
# Helpers
# ============================================================


async def device_code_exists(
    session: AsyncSession,
    device_code: str,
    *,
    exclude_device_id: uuid.UUID | None = None,
) -> bool:
    statement = select(Device.id).where(
        Device.device_code == device_code
    )

    if exclude_device_id is not None:
        statement = statement.where(
            Device.id != exclude_device_id
        )

    return (
        await session.scalar(statement)
    ) is not None


async def build_device_responses(
    session: AsyncSession,
    devices: list[Device],
) -> list[DeviceResponse]:
    """
    DeviceResponse with owner and activity counters, using one
    query each for owners and stats (no lazy loading).
    """

    owner_ids = {
        device.owner_id
        for device in devices
        if device.owner_id is not None
    }

    owners: dict[uuid.UUID, User] = {}
    if owner_ids:
        result = await session.execute(
            select(User).where(User.id.in_(owner_ids))
        )
        owners = {
            user.id: user
            for user in result.scalars().all()
        }

    stats = await activity.device_stats(
        session,
        [device.id for device in devices],
    )

    responses = []
    for device in devices:
        owner = owners.get(device.owner_id)
        device_stats = stats[device.id]

        responses.append(
            DeviceResponse(
                id=device.id,
                device_code=device.device_code,
                name=device.name,
                description=device.description,
                latitude=device.latitude,
                longitude=device.longitude,
                installed_at=device.installed_at,
                is_active=device.is_active,
                created_at=device.created_at,
                updated_at=device.updated_at,
                owner=(
                    DeviceOwnerSummary(
                        id=owner.id,
                        email=owner.email,
                        display_name=owner.display_name,
                    )
                    if owner
                    else None
                ),
                claimed_at=device.claimed_at,
                has_claim_code=device.claim_code_hash is not None,
                recording_count=device_stats.recording_count,
                detection_count=device_stats.detection_count,
                last_recording_at=device_stats.last_recording_at,
            )
        )

    return responses


async def build_device_response(
    session: AsyncSession,
    device: Device,
) -> DeviceResponse:
    return (
        await build_device_responses(
            session,
            [device],
        )
    )[0]


def ensure_not_system_device(
    device: Device,
) -> None:
    """
    The reserved MANUAL-UPLOAD device holds every user's manual
    analyses; it must never be owned, claimed or deleted.
    """

    if device.device_code == settings.manual_upload_device_code:
        raise PermissionDeniedError(
            "The manual-upload device is managed by the system."
        )


async def new_claim_code(
    device: Device,
) -> str:
    """
    Give `device` a fresh claim code; returns it in plain text (the
    only time it is ever available).
    """

    code = generate_claim_code()

    device.claim_code_hash = await asyncio.to_thread(
        hash_secret,
        normalize_claim_code(code),
    )

    return code


# ============================================================
# Create device (admin)
# ============================================================


@router.post(
    "",
    response_model=DeviceCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {
            "model": ErrorResponse,
            "description": "Device code already exists.",
        },
    },
)
async def create_device(
    data: DeviceCreate,
    admin: AdminUser,
    session: DatabaseSession,
) -> DeviceCreatedResponse:
    """
    Register a new monitoring device and generate its claim code.

    Give the device code and claim code to whoever will own the
    device; they add it to their account with POST /claim.
    """

    if await device_code_exists(session, data.device_code):
        raise DuplicateDeviceCodeError()

    device = Device(**data.model_dump())
    claim_code = await new_claim_code(device)

    session.add(device)

    try:
        await session.commit()

    except IntegrityError as exception:
        await session.rollback()
        # The unique constraint is the final guard against
        # concurrent duplicate requests.
        raise DuplicateDeviceCodeError() from exception

    await session.refresh(device)

    return DeviceCreatedResponse(
        device=await build_device_response(session, device),
        claim_code=claim_code,
    )


# ============================================================
# Claim a device (any signed-in user)
# ============================================================


@router.post(
    "/claim",
    response_model=DeviceResponse,
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Wrong device code or claim code.",
        },
        409: {
            "model": ErrorResponse,
            "description": "Device already belongs to someone.",
        },
    },
)
async def claim_device(
    data: DeviceClaimRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> DeviceResponse:
    """
    Link a device to your account using the device code and the
    claim code that came with it.
    """

    device = await session.scalar(
        select(Device).where(
            Device.device_code == data.device_code
        )
    )

    # Verify the code before revealing anything about the device
    # (including whether it is already owned).
    code_ok = await asyncio.to_thread(
        verify_secret,
        device.claim_code_hash if device else None,
        normalize_claim_code(data.claim_code),
    )

    if (
        device is None
        or not code_ok
        or device.device_code == settings.manual_upload_device_code
    ):
        raise InvalidDeviceClaimError()

    if device.owner_id is not None and device.owner_id != user.id:
        raise DeviceAlreadyClaimedError()

    if device.owner_id is None:
        device.owner_id = user.id
        device.claimed_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(device)

    return await build_device_response(session, device)


# ============================================================
# List / get devices
# ============================================================


@router.get(
    "",
    response_model=PaginatedResponse[DeviceResponse],
)
async def list_devices(
    user: CurrentUser,
    session: DatabaseSession,
    include_system: Annotated[
        bool,
        Query(description="Admins: also list the MANUAL-UPLOAD device."),
    ] = False,
    page: Annotated[
        int,
        Query(ge=1, description="Page number."),
    ] = 1,
    page_size: Annotated[
        int,
        Query(ge=1, le=100, description="Devices per page."),
    ] = 50,
    is_active: Annotated[
        bool | None,
        Query(description="Filter devices by active state."),
    ] = None,
    search: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=120,
            description="Search by device name or code.",
        ),
    ] = None,
) -> PaginatedResponse[DeviceResponse]:
    """
    Your devices (admins: every device), newest first.
    """

    conditions = []

    visibility = device_visibility(user)
    if visibility is not None:
        conditions.append(visibility)

    if not (include_system and user.is_admin):
        conditions.append(
            Device.device_code != settings.manual_upload_device_code
        )

    if is_active is not None:
        conditions.append(Device.is_active == is_active)

    if search and search.strip():
        pattern = f"%{search.strip()}%"
        conditions.append(
            or_(
                Device.name.ilike(pattern),
                Device.device_code.ilike(pattern),
            )
        )

    total_items = (
        await session.scalar(
            select(func.count(Device.id)).where(*conditions)
        )
    ) or 0

    result = await session.execute(
        select(Device)
        .where(*conditions)
        .order_by(Device.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return PaginatedResponse[DeviceResponse](
        items=await build_device_responses(
            session,
            list(result.scalars().all()),
        ),
        pagination=PaginationMetadata(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=(
                math.ceil(total_items / page_size)
                if total_items
                else 0
            ),
        ),
    )


@router.get(
    "/{device_id}",
    response_model=DeviceResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Device not found."},
    },
)
async def get_device(
    device_id: uuid.UUID,
    user: CurrentUser,
    session: DatabaseSession,
) -> DeviceResponse:
    device = await get_visible_device(session, user, device_id)

    return await build_device_response(session, device)


# ============================================================
# Device activity
# ============================================================


@router.get(
    "/{device_id}/summary",
    response_model=DeviceSummaryResponse,
)
async def get_device_summary(
    device_id: uuid.UUID,
    user: CurrentUser,
    session: DatabaseSession,
    days: Annotated[
        int,
        Query(ge=1, le=366, description="Days of daily activity."),
    ] = 30,
) -> DeviceSummaryResponse:
    """
    Totals, most-detected species and daily activity of a device.
    """

    device = await get_visible_device(session, user, device_id)
    scope = Recording.device_id == device.id

    first, last = await activity.recording_time_range(session, scope)

    return DeviceSummaryResponse(
        device_id=device.id,
        recording_count=await activity.count_recordings(session, scope),
        detection_count=await activity.count_detections(session, scope),
        species_count=await activity.count_detections(
            session, scope, distinct_species=True
        ),
        first_recording_at=first,
        last_recording_at=last,
        top_species=await activity.top_species(session, scope),
        daily_activity=await activity.daily_activity(
            session, scope, days=days
        ),
    )


@router.get(
    "/{device_id}/recordings",
    response_model=PaginatedResponse[TimelineRecording],
)
async def list_device_recordings(
    device_id: uuid.UUID,
    user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    date_from: Annotated[
        datetime | None,
        Query(description="Only ROIs recorded at or after this time."),
    ] = None,
    date_to: Annotated[
        datetime | None,
        Query(description="Only ROIs recorded before this time."),
    ] = None,
    only_with_detections: Annotated[
        bool,
        Query(description="Skip ROIs where BirdNET found nothing."),
    ] = False,
    minimum_confidence: Annotated[
        float | None,
        Query(ge=0, le=1, description="Hide weaker detections."),
    ] = None,
    species: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=180,
            description="Only ROIs with this species (scientific name).",
        ),
    ] = None,
) -> PaginatedResponse[TimelineRecording]:
    """
    A device's ROI snippets, newest first, each with its BirdNET
    detections and their real-world times.
    """

    device = await get_visible_device(session, user, device_id)

    conditions = [Recording.device_id == device.id]

    if date_from is not None:
        conditions.append(Recording.recorded_at >= date_from)

    if date_to is not None:
        conditions.append(Recording.recorded_at < date_to)

    if only_with_detections or species:
        detection_filter = [Detection.recording_id == Recording.id]

        if minimum_confidence is not None:
            detection_filter.append(
                Detection.confidence >= minimum_confidence
            )

        if species:
            detection_filter.append(
                func.lower(Detection.scientific_name)
                == species.strip().lower()
            )

        conditions.append(
            select(Detection.id).where(*detection_filter).exists()
        )

    total_items = (
        await session.scalar(
            select(func.count(Recording.id)).where(*conditions)
        )
    ) or 0

    result = await session.execute(
        select(Recording)
        .where(*conditions)
        .order_by(
            Recording.recorded_at.desc(),
            Recording.snippet_sequence.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return PaginatedResponse[TimelineRecording](
        items=await activity.timeline_for_recordings(
            session,
            list(result.scalars().all()),
            minimum_confidence=minimum_confidence,
        ),
        pagination=PaginationMetadata(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=(
                math.ceil(total_items / page_size)
                if total_items
                else 0
            ),
        ),
    )


# ============================================================
# Update / ownership
# ============================================================


@router.patch(
    "/{device_id}",
    response_model=DeviceResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Device not found."},
        409: {"model": ErrorResponse, "description": "Device code exists."},
    },
)
async def update_device(
    device_id: uuid.UUID,
    data: DeviceUpdate,
    user: CurrentUser,
    session: DatabaseSession,
) -> DeviceResponse:
    """
    Owners may edit name, description, location and install date;
    admins may also change the device code and active flag.
    """

    device = await get_visible_device(session, user, device_id)
    ensure_not_system_device(device)

    update_data = data.model_dump(exclude_unset=True)

    if not user.is_admin and not set(update_data) <= OWNER_EDITABLE_FIELDS:
        raise PermissionDeniedError(
            "Only an admin can change the device code or active state."
        )

    new_code = update_data.get("device_code")
    if (
        new_code is not None
        and new_code != device.device_code
        and await device_code_exists(
            session, new_code, exclude_device_id=device.id
        )
    ):
        raise DuplicateDeviceCodeError()

    for field_name, value in update_data.items():
        setattr(device, field_name, value)

    try:
        await session.commit()

    except IntegrityError as exception:
        await session.rollback()
        raise DuplicateDeviceCodeError() from exception

    await session.refresh(device)

    return await build_device_response(session, device)


@router.delete(
    "/{device_id}/owner",
    response_model=DeviceResponse,
)
async def release_device(
    device_id: uuid.UUID,
    user: CurrentUser,
    session: DatabaseSession,
) -> DeviceResponse:
    """
    Remove a device from its owner's account (owner or admin). Its
    recordings stay; whoever claims it next will see them.
    """

    device = await get_visible_device(session, user, device_id)
    ensure_not_system_device(device)

    device.owner_id = None
    device.claimed_at = None
    await session.commit()
    await session.refresh(device)

    return await build_device_response(session, device)


@router.put(
    "/{device_id}/owner",
    response_model=DeviceResponse,
)
async def assign_device_owner(
    device_id: uuid.UUID,
    data: DeviceOwnerAssignment,
    admin: AdminUser,
    session: DatabaseSession,
) -> DeviceResponse:
    """
    Admin: set (or clear) a device's owner directly.
    """

    device = await session.get(Device, device_id)
    if device is None:
        raise DeviceNotFoundError()

    ensure_not_system_device(device)

    owner: User | None = None
    if data.owner_id is not None:
        owner = await session.get(User, data.owner_id)
    elif data.owner_email is not None:
        owner = await session.scalar(
            select(User).where(User.email == data.owner_email.lower())
        )

    if (data.owner_id or data.owner_email) and owner is None:
        raise UserNotFoundError()

    device.owner_id = owner.id if owner else None
    device.claimed_at = datetime.now(timezone.utc) if owner else None
    await session.commit()
    await session.refresh(device)

    return await build_device_response(session, device)


@router.post(
    "/{device_id}/claim-code",
    response_model=ClaimCodeResponse,
)
async def regenerate_claim_code(
    device_id: uuid.UUID,
    admin: AdminUser,
    session: DatabaseSession,
) -> ClaimCodeResponse:
    """
    Admin: issue a new claim code (the old one stops working).
    """

    device = await session.get(Device, device_id)
    if device is None:
        raise DeviceNotFoundError()

    ensure_not_system_device(device)

    claim_code = await new_claim_code(device)
    await session.commit()

    return ClaimCodeResponse(
        device_id=device.id,
        device_code=device.device_code,
        claim_code=claim_code,
    )


# ============================================================
# Delete device (admin)
# ============================================================


@router.delete(
    "/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"model": ErrorResponse, "description": "Device not found."},
    },
)
async def delete_device(
    device_id: uuid.UUID,
    admin: AdminUser,
    session: DatabaseSession,
) -> Response:
    """
    Delete a device together with its recordings and detections.
    """

    device = await session.get(Device, device_id)
    if device is None:
        raise DeviceNotFoundError()

    ensure_not_system_device(device)

    await session.delete(device)
    await session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
