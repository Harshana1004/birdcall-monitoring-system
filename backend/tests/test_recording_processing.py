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
    ProcessingStatus,
    Recording,
)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        print(
            "Recording processing database test"
        )

        print(
            "=" * 60
        )

        # ----------------------------------------------------
        # Processing-status counts
        # ----------------------------------------------------

        for processing_status in (
            ProcessingStatus
        ):
            count = (
                await session.scalar(
                    select(
                        func.count(
                            Recording.id
                        )
                    )
                    .where(
                        Recording.processing_status
                        == processing_status
                    )
                )
            ) or 0

            print(
                f"{processing_status.value:12s}: "
                f"{count}"
            )

        # ----------------------------------------------------
        # Detection count
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

        print()
        print(
            f"Stored detections: "
            f"{detection_count}"
        )

        # ----------------------------------------------------
        # Show latest completed recording
        # ----------------------------------------------------

        result = await session.execute(
            select(Recording)
            .where(
                Recording.processing_status
                == ProcessingStatus.COMPLETED
            )
            .order_by(
                Recording.processed_at.desc()
            )
            .limit(1)
        )

        recording = (
            result.scalar_one_or_none()
        )

        if recording is None:
            print(
                "No completed recording exists yet."
            )

        else:
            print()
            print(
                "Latest completed recording"
            )

            print(
                "-" * 60
            )

            print(
                f"ID: {recording.id}"
            )

            print(
                f"File: "
                f"{recording.original_filename}"
            )

            print(
                f"Status: "
                f"{recording.processing_status.value}"
            )

            detection_result = (
                await session.execute(
                    select(Detection)
                    .where(
                        Detection.recording_id
                        == recording.id
                    )
                    .order_by(
                        Detection.confidence.desc()
                    )
                )
            )

            detections = (
                detection_result
                .scalars()
                .all()
            )

            print(
                f"Detections: "
                f"{len(detections)}"
            )

            for detection in detections:
                print(
                    f"  "
                    f"{detection.common_name} "
                    f"({detection.confidence:.3f})"
                )

        print()
        print(
            "Processing database test: PASS"
        )


if __name__ == "__main__":
    asyncio.run(
        main()
    )