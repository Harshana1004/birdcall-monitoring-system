import asyncio

from sqlalchemy import (
    func,
    select,
)

from src.database import (
    AsyncSessionLocal,
)
from src.models import (
    Detection,
)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        # ----------------------------------------------------
        # Count detections
        # ----------------------------------------------------

        detection_count = (
            await session.scalar(
                select(
                    func.count(
                        Detection.id
                    )
                )
            )
        ) or 0

        print(
            "Detection database test"
        )

        print(
            "=" * 50
        )

        print(
            f"Total detections: "
            f"{detection_count}"
        )

        # ----------------------------------------------------
        # Retrieve recent detections
        # ----------------------------------------------------

        result = await session.execute(
            select(Detection)
            .order_by(
                Detection.created_at.desc()
            )
            .limit(10)
        )

        detections = (
            result.scalars()
            .all()
        )

        print()
        print(
            f"Recent detections found: "
            f"{len(detections)}"
        )

        print(
            "-" * 50
        )

        for detection in detections:
            print(
                f"ID: {detection.id}"
            )

            print(
                f"Recording: "
                f"{detection.recording_id}"
            )

            print(
                f"Species: "
                f"{detection.common_name}"
            )

            print(
                f"Scientific: "
                f"{detection.scientific_name}"
            )

            print(
                f"Confidence: "
                f"{detection.confidence:.4f}"
            )

            print(
                f"Interval: "
                f"{detection.start_time_seconds:.2f}s "
                f"- "
                f"{detection.end_time_seconds:.2f}s"
            )

            print(
                "-" * 50
            )


if __name__ == "__main__":
    asyncio.run(
        main()
    )