import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.device import Device


class DeviceRepository:
    """Database operations for monitoring devices."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, device: Device) -> Device:
        self.session.add(device)

        await self.session.flush()
        await self.session.refresh(device)

        return device

    async def get_by_id(
        self,
        device_id: uuid.UUID,
    ) -> Device | None:
        statement = select(Device).where(
            Device.id == device_id,
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_code(
        self,
        device_code: str,
    ) -> Device | None:
        statement = select(Device).where(
            Device.device_code == device_code,
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        offset: int,
        limit: int,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> list[Device]:
        statement = select(Device)

        if is_active is not None:
            statement = statement.where(
                Device.is_active == is_active,
            )

        if search:
            search_pattern = f"%{search.strip()}%"

            statement = statement.where(
                Device.name.ilike(search_pattern)
                | Device.device_code.ilike(search_pattern)
            )

        statement = (
            statement
            .order_by(Device.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(statement)

        return list(result.scalars().all())

    async def count(
        self,
        *,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> int:
        statement = select(func.count(Device.id))

        if is_active is not None:
            statement = statement.where(
                Device.is_active == is_active,
            )

        if search:
            search_pattern = f"%{search.strip()}%"

            statement = statement.where(
                Device.name.ilike(search_pattern)
                | Device.device_code.ilike(search_pattern)
            )

        result = await self.session.execute(statement)

        return result.scalar_one()

    async def delete(self, device: Device) -> None:
        await self.session.delete(device)
        await self.session.flush()