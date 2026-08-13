import asyncio

from sqlalchemy import (
    func,
    select,
)

from src.database import (
    AsyncSessionLocal,
)
from src.models import (
    Recording,
)
from src.services.recordings import (
    RecordingService,
)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        print(
            "Recording service test"
        )

        print(
            "=" * 60
        )

        # ----------------------------------------------------
        # Count existing recordings
        # ----------------------------------------------------

        total_recordings = (
            await session.scalar(
                select(
                    func.count(
                        Recording.id
                    )
                )
            )
        ) or 0

        print(
            f"Existing recordings: "
            f"{total_recordings}"
        )

        # ----------------------------------------------------
        # Test list method
        # ----------------------------------------------------

        service = RecordingService(
            session
        )

        response = (
            await service.list_recordings(
                page=1,
                page_size=20,
            )
        )

        print(
            f"Returned recordings: "
            f"{len(response.items)}"
        )

        print(
            f"Total items: "
            f"{response.pagination.total_items}"
        )

        print(
            f"Total pages: "
            f"{response.pagination.total_pages}"
        )

        assert (
            response.pagination.total_items
            == total_recordings
        )

        # ----------------------------------------------------
        # Test get method using existing row
        # ----------------------------------------------------

        result = await session.execute(
            select(Recording)
            .order_by(
                Recording.uploaded_at.desc()
            )
            .limit(1)
        )

        existing_recording = (
            result.scalar_one_or_none()
        )

        if existing_recording is None:
            print()
            print(
                "No recordings currently exist, "
                "so get_recording test was skipped."
            )

        else:
            retrieved = (
                await service.get_recording(
                    existing_recording.id
                )
            )

            assert (
                retrieved.id
                == existing_recording.id
            )

            print()
            print(
                "Latest recording"
            )

            print(
                "-" * 60
            )

            print(
                f"ID: {retrieved.id}"
            )

            print(
                f"Device: "
                f"{retrieved.device_id}"
            )

            print(
                f"File: "
                f"{retrieved.original_filename}"
            )

            print(
                f"Duration: "
                f"{retrieved.duration_seconds:.3f}s"
            )

            print(
                f"Status: "
                f"{retrieved.processing_status.value}"
            )

            print(
                f"Path: "
                f"{retrieved.file_path}"
            )

        print()
        print(
            "Recording service: PASS"
        )


if __name__ == "__main__":
    asyncio.run(
        main()
    )