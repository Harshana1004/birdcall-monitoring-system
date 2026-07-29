import asyncio
import uuid

from core.db import AsyncSessionLocal
from services.recording_processing_service import (
    RecordingProcessingService,
)


RECORDING_ID = uuid.UUID(
    "1a70ea59-d302-4b4c-a824-fe0b6afd6bba"
)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        service = RecordingProcessingService(
            session=session
        )

        await service.process_recording(
            RECORDING_ID
        )

    print(
        "Recording processing test completed."
    )


if __name__ == "__main__":
    asyncio.run(main())