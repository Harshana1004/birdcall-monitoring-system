from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import (
    func,
    select,
)

from src.core.config import settings
from src.database import (
    AsyncSessionLocal,
)
from src.models import (
    Detection,
    Device,
    ProcessingStatus,
    Recording,
)
from src.services.manual_analysis import (
    ManualAnalysisService,
    get_or_create_manual_device,
)


async def main() -> None:
    # ========================================================
    # Command-line input
    # ========================================================

    if len(sys.argv) != 2:
        print(
            "Usage:"
        )

        print(
            "python -m tests.test_manual_analysis "
            "\"path/to/raw_recording.wav\""
        )

        raise SystemExit(
            1
        )

    source_path = Path(
        sys.argv[1]
    ).resolve()

    if not source_path.exists():
        raise FileNotFoundError(
            f"Test audio file was not found: "
            f"{source_path}"
        )

    if not source_path.is_file():
        raise ValueError(
            f"Test audio path is not a file: "
            f"{source_path}"
        )

    print()
    print(
        "=" * 70
    )

    print(
        "Manual Audio Analysis Integration Test"
    )

    print(
        "=" * 70
    )

    print(
        f"Input file: "
        f"{source_path}"
    )

    print()

    # ========================================================
    # Database session
    # ========================================================

    async with AsyncSessionLocal() as session:
        # ----------------------------------------------------
        # Record database state before analysis
        # ----------------------------------------------------

        recordings_before = (
            await session.scalar(
                select(
                    func.count(
                        Recording.id
                    )
                )
            )
        ) or 0

        detections_before = (
            await session.scalar(
                select(
                    func.count(
                        Detection.id
                    )
                )
            )
        ) or 0

        # ----------------------------------------------------
        # Verify/create MANUAL-UPLOAD device
        # ----------------------------------------------------

        manual_device = (
            await get_or_create_manual_device(
                session
            )
        )

        print(
            "Manual upload device"
        )

        print(
            "-" * 70
        )

        print(
            f"ID: "
            f"{manual_device.id}"
        )

        print(
            f"Code: "
            f"{manual_device.device_code}"
        )

        print(
            f"Name: "
            f"{manual_device.name}"
        )

        print(
            f"Active: "
            f"{manual_device.is_active}"
        )

        assert (
            manual_device.device_code
            == settings.manual_upload_device_code
        )

        assert (
            manual_device.is_active
            is True
        )

        print()

        # ----------------------------------------------------
        # Run complete analysis
        # ----------------------------------------------------

        service = (
            ManualAnalysisService(
                session
            )
        )

        print(
            "Running preprocessing + BirdNET..."
        )

        print()

        result = (
            await service.analyze_file(
                source_file_path=(
                    source_path
                ),
                original_filename=(
                    source_path.name
                ),
            )
        )

        # ====================================================
        # Processing output
        # ====================================================

        processing = (
            result.processing_result
        )

        print(
            "Audio processing"
        )

        print(
            "-" * 70
        )

        print(
            f"Capture session: "
            f"{result.capture_session_id}"
        )

        print(
            f"Original filename: "
            f"{result.original_filename}"
        )

        print(
            f"Stored original: "
            f"{result.original_file_path}"
        )

        print(
            f"Sample rate: "
            f"{processing.sample_rate} Hz"
        )

        print(
            f"Duration: "
            f"{processing.duration_seconds:.3f} s"
        )

        print(
            f"Energy frames: "
            f"{len(processing.energy)}"
        )

        print(
            f"Energy threshold: "
            f"{processing.energy_threshold:.8f}"
        )

        print(
            f"Detected ROIs: "
            f"{len(processing.rois)}"
        )

        print()

        # ----------------------------------------------------
        # Verify original file storage
        # ----------------------------------------------------

        assert (
            result.original_file_path.exists()
        )

        assert (
            result.original_file_path.is_file()
        )

        assert (
            processing.sample_rate
            == 16000
        )

        # ====================================================
        # ROI results
        # ====================================================

        print(
            "Persisted ROI recordings"
        )

        print(
            "-" * 70
        )

        if not result.recordings:
            print(
                "No ROIs were detected."
            )

        for index, roi_result in enumerate(
            result.recordings
        ):
            recording = (
                roi_result.recording
            )

            print(
                f"ROI {index}"
            )

            print(
                f"  Recording ID: "
                f"{recording.id}"
            )

            print(
                f"  Sequence: "
                f"{recording.snippet_sequence}"
            )

            print(
                f"  ROI interval: "
                f"{recording.roi_start_seconds:.3f}"
                f" - "
                f"{recording.roi_end_seconds:.3f} s"
            )

            print(
                f"  Stored duration: "
                f"{recording.duration_seconds:.3f} s"
            )

            print(
                f"  Status: "
                f"{recording.processing_status.value}"
            )

            print(
                f"  Stored WAV: "
                f"{recording.file_path}"
            )

            print(
                f"  BirdNET detections: "
                f"{len(roi_result.detections)}"
            )

            for detection in (
                roi_result.detections
            ):
                print(
                    "    "
                    f"{detection.common_name} "
                    f"({detection.scientific_name}) "
                    f"- "
                    f"{detection.confidence:.4f}"
                )

            print()

            # -----------------------------------------------
            # Structural checks
            # -----------------------------------------------

            assert (
                recording.device_id
                == manual_device.id
            )

            assert (
                recording.capture_session_id
                == result.capture_session_id
            )

            assert (
                recording.snippet_sequence
                == index
            )

            assert (
                recording.edge_processing_version
                == "backend-analysis-1.0.0"
            )

            assert (
                Path(
                    recording.file_path
                ).exists()
            )

            assert (
                recording.processing_status
                in {
                    ProcessingStatus.COMPLETED,
                    ProcessingStatus.FAILED,
                }
            )

        # ====================================================
        # Retrieve session from PostgreSQL
        # ====================================================

        stored_recordings = (
            await service.get_session_recordings(
                result.capture_session_id
            )
        )

        stored_detections = (
            await service.get_session_detections(
                result.capture_session_id
            )
        )

        assert (
            len(
                stored_recordings
            )
            == len(
                result.recordings
            )
        )

        print(
            "Database retrieval"
        )

        print(
            "-" * 70
        )

        print(
            f"Recordings retrieved by session: "
            f"{len(stored_recordings)}"
        )

        print(
            f"Detections retrieved by session: "
            f"{len(stored_detections)}"
        )

        print()

        # ====================================================
        # Database totals
        # ====================================================

        recordings_after = (
            await session.scalar(
                select(
                    func.count(
                        Recording.id
                    )
                )
            )
        ) or 0

        detections_after = (
            await session.scalar(
                select(
                    func.count(
                        Detection.id
                    )
                )
            )
        ) or 0

        print(
            "Database changes"
        )

        print(
            "-" * 70
        )

        print(
            f"Recordings before: "
            f"{recordings_before}"
        )

        print(
            f"Recordings after: "
            f"{recordings_after}"
        )

        print(
            f"Recordings added: "
            f"{recordings_after - recordings_before}"
        )

        print()

        print(
            f"Detections before: "
            f"{detections_before}"
        )

        print(
            f"Detections after: "
            f"{detections_after}"
        )

        print(
            f"Detections added: "
            f"{detections_after - detections_before}"
        )

        print()

        # ====================================================
        # Verify MANUAL-UPLOAD is unique
        # ====================================================

        manual_device_count = (
            await session.scalar(
                select(
                    func.count(
                        Device.id
                    )
                )
                .where(
                    Device.device_code
                    == settings.manual_upload_device_code
                )
            )
        ) or 0

        assert (
            manual_device_count
            == 1
        )

        print(
            f"MANUAL-UPLOAD device count: "
            f"{manual_device_count}"
        )

        print()

        # ====================================================
        # Overall result
        # ====================================================

        failed_recordings = [
            item.recording
            for item in result.recordings
            if (
                item.recording.processing_status
                == ProcessingStatus.FAILED
            )
        ]

        print(
            "=" * 70
        )

        if failed_recordings:
            print(
                "Manual analysis completed, but one or more "
                "BirdNET jobs FAILED."
            )

            for recording in (
                failed_recordings
            ):
                print(
                    f"{recording.id}: "
                    f"{recording.processing_error}"
                )

        else:
            print(
                "Manual analysis integration test: PASS"
            )

        print(
            "=" * 70
        )


if __name__ == "__main__":
    asyncio.run(
        main()
    )