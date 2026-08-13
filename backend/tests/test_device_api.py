import asyncio

from sqlalchemy import select

from src.database import (
    AsyncSessionLocal,
)
from src.models import Device


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Device)
            .order_by(
                Device.created_at.desc()
            )
            .limit(10)
        )

        devices = (
            result.scalars().all()
        )

        print(
            f"Devices found: {len(devices)}"
        )

        for device in devices:
            print(
                device.id,
                device.device_code,
                device.name,
                device.is_active,
            )


if __name__ == "__main__":
    asyncio.run(
        main()
    )