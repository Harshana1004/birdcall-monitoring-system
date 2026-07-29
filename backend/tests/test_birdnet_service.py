import asyncio
from pathlib import Path

from services.birdnet_service import BirdNetService


AUDIO_FILE = Path(
    "storage/audio/"
    "14fca5f8-3fdb-4255-b5a9-d3fdd0c4c289/"
    "1a70ea59-d302-4b4c-a824-fe0b6afd6bba.wav"
)


async def main() -> None:
    service = BirdNetService()

    predictions = await service.analyze(
        AUDIO_FILE
    )

    print(
        f"Retained predictions: {len(predictions)}"
    )

    for prediction in predictions:
        print(
            f"{prediction.start_time_seconds:.2f}s - "
            f"{prediction.end_time_seconds:.2f}s | "
            f"{prediction.scientific_name} | "
            f"{prediction.common_name} | "
            f"{prediction.confidence:.4f}"
        )


if __name__ == "__main__":
    asyncio.run(main())