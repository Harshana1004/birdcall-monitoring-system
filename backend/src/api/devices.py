import math
import uuid
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

from src.api.schemas import (
    DeviceCreate,
    DeviceResponse,
    DeviceUpdate,
    ErrorResponse,
    PaginatedResponse,
    PaginationMetadata,
)
from src.core.exceptions import (
    DeviceNotFoundError,
    DuplicateDeviceCodeError,
)
from src.database import get_db
from src.models import Device


router = APIRouter(
    prefix="/api/v1/devices",
    tags=["Devices"],
)


# ============================================================
# Database dependency
# ============================================================


DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db),
]


# ============================================================
# Helpers
# ============================================================


async def get_device_or_raise(
    session: AsyncSession,
    device_id: uuid.UUID,
) -> Device:
    """
    Retrieve a device by UUID or raise a 404 application error.
    """

    device = await session.get(
        Device,
        device_id,
    )

    if device is None:
        raise DeviceNotFoundError()

    return device


async def device_code_exists(
    session: AsyncSession,
    device_code: str,
    *,
    exclude_device_id: uuid.UUID | None = None,
) -> bool:
    """
    Return True if another device already uses the code.
    """

    statement = select(
        Device.id
    ).where(
        Device.device_code
        == device_code
    )

    if exclude_device_id is not None:
        statement = statement.where(
            Device.id
            != exclude_device_id
        )

    result = await session.execute(
        statement
    )

    return (
        result.scalar_one_or_none()
        is not None
    )


# ============================================================
# Create device
# ============================================================


@router.post(
    "",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {
            "model": ErrorResponse,
            "description": (
                "Device code already exists."
            ),
        },
    },
)
async def create_device(
    data: DeviceCreate,
    session: DatabaseSession,
) -> DeviceResponse:
    """
    Register a new monitoring device.
    """

    if await device_code_exists(
        session,
        data.device_code,
    ):
        raise DuplicateDeviceCodeError()

    device = Device(
        **data.model_dump()
    )

    session.add(
        device
    )

    try:
        await session.commit()

    except IntegrityError as exception:
        await session.rollback()

        # The unique database constraint remains the final
        # protection against concurrent duplicate requests.
        raise DuplicateDeviceCodeError() from exception

    await session.refresh(
        device
    )

    return DeviceResponse.model_validate(
        device
    )


# ============================================================
# List devices
# ============================================================


@router.get(
    "",
    response_model=PaginatedResponse[
        DeviceResponse
    ],
)
async def list_devices(
    session: DatabaseSession,
    page: Annotated[
        int,
        Query(
            ge=1,
            description="Page number.",
        ),
    ] = 1,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description=(
                "Number of devices returned per page."
            ),
        ),
    ] = 20,
    is_active: Annotated[
        bool | None,
        Query(
            description=(
                "Filter devices by active state."
            ),
        ),
    ] = None,
    search: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=120,
            description=(
                "Search using a device name "
                "or device code."
            ),
        ),
    ] = None,
) -> PaginatedResponse[
    DeviceResponse
]:
    """
    Return a paginated list of monitoring devices.
    """

    conditions = []

    if is_active is not None:
        conditions.append(
            Device.is_active
            == is_active
        )

    if search is not None:
        normalized_search = (
            search.strip()
        )

        if normalized_search:
            pattern = (
                f"%{normalized_search}%"
            )

            conditions.append(
                or_(
                    Device.name.ilike(
                        pattern
                    ),
                    Device.device_code.ilike(
                        pattern
                    ),
                )
            )

    # --------------------------------------------------------
    # Count matching rows
    # --------------------------------------------------------

    count_statement = select(
        func.count(
            Device.id
        )
    )

    if conditions:
        count_statement = (
            count_statement.where(
                *conditions
            )
        )

    total_items = (
        await session.scalar(
            count_statement
        )
    ) or 0

    # --------------------------------------------------------
    # Retrieve current page
    # --------------------------------------------------------

    offset = (
        page - 1
    ) * page_size

    statement = (
        select(Device)
        .order_by(
            Device.created_at.desc()
        )
        .offset(offset)
        .limit(page_size)
    )

    if conditions:
        statement = statement.where(
            *conditions
        )

    result = await session.execute(
        statement
    )

    devices = (
        result.scalars()
        .all()
    )

    total_pages = (
        math.ceil(
            total_items
            / page_size
        )
        if total_items > 0
        else 0
    )

    return PaginatedResponse[
        DeviceResponse
    ](
        items=[
            DeviceResponse.model_validate(
                device
            )
            for device in devices
        ],
        pagination=PaginationMetadata(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
    )


# ============================================================
# Get device
# ============================================================


@router.get(
    "/{device_id}",
    response_model=DeviceResponse,
    responses={
        404: {
            "model": ErrorResponse,
            "description": (
                "Device not found."
            ),
        },
    },
)
async def get_device(
    device_id: uuid.UUID,
    session: DatabaseSession,
) -> DeviceResponse:
    """
    Return one monitoring device.
    """

    device = await get_device_or_raise(
        session,
        device_id,
    )

    return DeviceResponse.model_validate(
        device
    )


# ============================================================
# Update device
# ============================================================


@router.patch(
    "/{device_id}",
    response_model=DeviceResponse,
    responses={
        404: {
            "model": ErrorResponse,
            "description": (
                "Device not found."
            ),
        },
        409: {
            "model": ErrorResponse,
            "description": (
                "Device code already exists."
            ),
        },
    },
)
async def update_device(
    device_id: uuid.UUID,
    data: DeviceUpdate,
    session: DatabaseSession,
) -> DeviceResponse:
    """
    Partially update a monitoring device.
    """

    device = await get_device_or_raise(
        session,
        device_id,
    )

    update_data = data.model_dump(
        exclude_unset=True,
    )

    new_device_code = (
        update_data.get(
            "device_code"
        )
    )

    if (
        new_device_code is not None
        and new_device_code
        != device.device_code
    ):
        if await device_code_exists(
            session,
            new_device_code,
            exclude_device_id=device.id,
        ):
            raise DuplicateDeviceCodeError()

    for field_name, value in (
        update_data.items()
    ):
        setattr(
            device,
            field_name,
            value,
        )

    try:
        await session.commit()

    except IntegrityError as exception:
        await session.rollback()

        raise DuplicateDeviceCodeError() from exception

    await session.refresh(
        device
    )

    return DeviceResponse.model_validate(
        device
    )


# ============================================================
# Delete device
# ============================================================


@router.delete(
    "/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {
            "model": ErrorResponse,
            "description": (
                "Device not found."
            ),
        },
    },
)
async def delete_device(
    device_id: uuid.UUID,
    session: DatabaseSession,
) -> Response:
    """
    Delete a monitoring device.

    Related Recording rows and their Detection rows are removed
    through the existing cascade relationships/database foreign
    keys.
    """

    device = await get_device_or_raise(
        session,
        device_id,
    )

    await session.delete(
        device
    )

    await session.commit()

    return Response(
        status_code=(
            status.HTTP_204_NO_CONTENT
        )
    )