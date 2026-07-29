import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Query,
    Response,
    status,
)

from api.dependencies import (
    DatabaseSession,
    PageNumber,
    PageSize,
)
from schemas.common import (
    ErrorResponse,
    PaginatedResponse,
)
from schemas.device import (
    DeviceCreate,
    DeviceResponse,
    DeviceUpdate,
)
from services.device_service import DeviceService


router = APIRouter(
    prefix="/api/v1/devices",
    tags=["Devices"],
)


@router.post(
    "",
    response_model=DeviceResponse,
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
    session: DatabaseSession,
) -> DeviceResponse:
    service = DeviceService(session)

    device = await service.create_device(data)

    return DeviceResponse.model_validate(device)


@router.get(
    "",
    response_model=PaginatedResponse[DeviceResponse],
)
async def list_devices(
    session: DatabaseSession,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    is_active: bool | None = None,
    search: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=120,
            description=(
                "Search using a device name or device code."
            ),
        ),
    ] = None,
) -> PaginatedResponse[DeviceResponse]:
    service = DeviceService(session)

    return await service.list_devices(
        page=page,
        page_size=page_size,
        is_active=is_active,
        search=search,
    )


@router.get(
    "/{device_id}",
    response_model=DeviceResponse,
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Device not found.",
        },
    },
)
async def get_device(
    device_id: uuid.UUID,
    session: DatabaseSession,
) -> DeviceResponse:
    service = DeviceService(session)

    device = await service.get_device(device_id)

    return DeviceResponse.model_validate(device)


@router.patch(
    "/{device_id}",
    response_model=DeviceResponse,
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Device not found.",
        },
        409: {
            "model": ErrorResponse,
            "description": "Device code already exists.",
        },
    },
)
async def update_device(
    device_id: uuid.UUID,
    data: DeviceUpdate,
    session: DatabaseSession,
) -> DeviceResponse:
    service = DeviceService(session)

    device = await service.update_device(
        device_id,
        data,
    )

    return DeviceResponse.model_validate(device)


@router.delete(
    "/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Device not found.",
        },
    },
)
async def delete_device(
    device_id: uuid.UUID,
    session: DatabaseSession,
) -> Response:
    service = DeviceService(session)

    await service.delete_device(device_id)

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )