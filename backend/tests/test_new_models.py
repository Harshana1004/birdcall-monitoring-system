import asyncio

from sqlalchemy import func, select

from src.database import AsyncSessionLocal
from src.models import (
    Detection,
    Device,
    Recording,
)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        device_count = await session.scalar(
            select(
                func.count(
                    Device.id
                )
            )
        )

        recording_count = await session.scalar(
            select(
                func.count(
                    Recording.id
                )
            )
        )

        detection_count = await session.scalar(
            select(
                func.count(
                    Detection.id
                )
            )
        )

        print(
            "Existing database rows"
        )

        print(
            "=" * 40
        )

        print(
            f"Devices:    {device_count}"
        )

        print(
            f"Recordings: {recording_count}"
        )

        print(
            f"Detections: {detection_count}"
        )


if __name__ == "__main__":
    asyncio.run(
        main()
    )