import math
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
)
from models.device import Device
from repositories.device_repository import DeviceRepository
from schemas.common import (
    PaginatedResponse,
    PaginationMetadata,
)
from schemas.device import (
    DeviceCreate,
    DeviceResponse,
    DeviceUpdate,
)


class DeviceService:
    """Business logic for monitoring devices."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = DeviceRepository(session)

    async def create_device(
        self,
        data: DeviceCreate,
    ) -> Device:
        existing_device = await self.repository.get_by_code(
            data.device_code,
        )

        if existing_device is not None:
            raise ResourceConflictError(
                f"A device with code '{data.device_code}' "
                "already exists."
            )

        device = Device(
            **data.model_dump(),
        )

        try:
            await self.repository.create(device)
            await self.session.commit()

        except IntegrityError as exception:
            await self.session.rollback()

            raise ResourceConflictError(
                "The device could not be created because "
                "one of its unique values already exists."
            ) from exception

        return device

    async def get_device(
        self,
        device_id: uuid.UUID,
    ) -> Device:
        device = await self.repository.get_by_id(device_id)

        if device is None:
            raise ResourceNotFoundError(
                f"Device '{device_id}' was not found."
            )

        return device

    async def list_devices(
        self,
        *,
        page: int,
        page_size: int,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> PaginatedResponse[DeviceResponse]:
        offset = (page - 1) * page_size

        devices = await self.repository.list(
            offset=offset,
            limit=page_size,
            is_active=is_active,
            search=search,
        )

        total_items = await self.repository.count(
            is_active=is_active,
            search=search,
        )

        total_pages = (
            math.ceil(total_items / page_size)
            if total_items > 0
            else 0
        )

        return PaginatedResponse[DeviceResponse](
            items=[
                DeviceResponse.model_validate(device)
                for device in devices
            ],
            pagination=PaginationMetadata(
                page=page,
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
            ),
        )

    async def update_device(
        self,
        device_id: uuid.UUID,
        data: DeviceUpdate,
    ) -> Device:
        device = await self.get_device(device_id)

        update_data = data.model_dump(
            exclude_unset=True,
        )

        if not update_data:
            return device

        new_device_code = update_data.get("device_code")

        if (
            new_device_code is not None
            and new_device_code != device.device_code
        ):
            existing_device = await self.repository.get_by_code(
                new_device_code,
            )

            if existing_device is not None:
                raise ResourceConflictError(
                    f"A device with code '{new_device_code}' "
                    "already exists."
                )

        for field_name, value in update_data.items():
            setattr(device, field_name, value)

        try:
            await self.session.flush()
            await self.session.commit()
            await self.session.refresh(device)

        except IntegrityError as exception:
            await self.session.rollback()

            raise ResourceConflictError(
                "The device could not be updated because "
                "one of its unique values already exists."
            ) from exception

        return device

    async def delete_device(
        self,
        device_id: uuid.UUID,
    ) -> None:
        device = await self.get_device(device_id)

        await self.repository.delete(device)
        await self.session.commit()