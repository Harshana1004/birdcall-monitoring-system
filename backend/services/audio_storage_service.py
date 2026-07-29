import asyncio
import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import aiofiles
import soundfile
from fastapi import UploadFile

from core.config import settings
from core.exceptions import (
    FileTooLargeError,
    InvalidFileError,
)


UPLOAD_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class StoredAudioFile:
    """Metadata for a staged or permanently stored audio file."""

    original_filename: str
    stored_filename: str
    file_path: Path
    checksum_sha256: str
    file_size_bytes: int
    duration_seconds: float
    sample_rate: int
    channel_count: int


class AudioStorageService:
    """Validate, stage and permanently store uploaded audio files."""

    def __init__(self) -> None:
        self.storage_directory = (
            settings.audio_storage_directory.resolve()
        )

    async def stage_upload(
        self,
        upload: UploadFile,
    ) -> StoredAudioFile:
        """
        Stream an upload into temporary storage.

        The file is validated, hashed and inspected before it is moved
        into permanent storage.
        """

        original_filename = self._validate_filename(upload)

        temporary_directory = (
            self.storage_directory / ".temporary"
        )

        temporary_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_filename = f"{uuid.uuid4().hex}.upload"
        temporary_path = temporary_directory / temporary_filename

        checksum = hashlib.sha256()
        total_size = 0

        try:
            async with aiofiles.open(
                temporary_path,
                mode="wb",
            ) as temporary_file:
                while True:
                    chunk = await upload.read(
                        UPLOAD_CHUNK_SIZE
                    )

                    if not chunk:
                        break

                    total_size += len(chunk)

                    if total_size > settings.max_upload_size_bytes:
                        raise FileTooLargeError(
                            "The uploaded file exceeds the "
                            f"{settings.max_upload_size_mb} MB "
                            "size limit."
                        )

                    checksum.update(chunk)

                    await temporary_file.write(chunk)

            if total_size == 0:
                raise InvalidFileError(
                    "The uploaded audio file is empty."
                )

            metadata = await asyncio.to_thread(
                self._read_audio_metadata,
                temporary_path,
            )

            return StoredAudioFile(
                original_filename=original_filename,
                stored_filename=temporary_filename,
                file_path=temporary_path,
                checksum_sha256=checksum.hexdigest(),
                file_size_bytes=total_size,
                duration_seconds=metadata[
                    "duration_seconds"
                ],
                sample_rate=metadata["sample_rate"],
                channel_count=metadata["channel_count"],
            )

        except Exception:
            temporary_path.unlink(
                missing_ok=True,
            )
            raise

        finally:
            await upload.close()

    async def finalize_upload(
        self,
        staged_file: StoredAudioFile,
        *,
        device_id: uuid.UUID,
        recording_id: uuid.UUID,
    ) -> StoredAudioFile:
        """Move a staged file into permanent device storage."""

        device_directory = (
            self.storage_directory / str(device_id)
        )

        device_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        stored_filename = f"{recording_id}.wav"
        final_path = device_directory / stored_filename

        if final_path.exists():
            raise InvalidFileError(
                "A stored audio file with this identifier "
                "already exists."
            )

        await asyncio.to_thread(
            os.replace,
            staged_file.file_path,
            final_path,
        )

        return StoredAudioFile(
            original_filename=staged_file.original_filename,
            stored_filename=stored_filename,
            file_path=final_path,
            checksum_sha256=staged_file.checksum_sha256,
            file_size_bytes=staged_file.file_size_bytes,
            duration_seconds=staged_file.duration_seconds,
            sample_rate=staged_file.sample_rate,
            channel_count=staged_file.channel_count,
        )

    async def delete_file(
        self,
        file_path: Path | str,
    ) -> None:
        """Delete a stored or staged file if it exists."""

        path = Path(file_path)

        await asyncio.to_thread(
            path.unlink,
            missing_ok=True,
        )

    def _validate_filename(
        self,
        upload: UploadFile,
    ) -> str:
        if not upload.filename:
            raise InvalidFileError(
                "The uploaded file must have a filename."
            )

        original_filename = Path(upload.filename).name

        extension = (
            Path(original_filename)
            .suffix
            .lower()
            .lstrip(".")
        )

        if extension not in settings.allowed_audio_extension_set:
            allowed_extensions = ", ".join(
                sorted(settings.allowed_audio_extension_set)
            )

            raise InvalidFileError(
                "Unsupported audio file extension. "
                f"Allowed extensions: {allowed_extensions}."
            )

        return original_filename

    @staticmethod
    def _read_audio_metadata(
        file_path: Path,
    ) -> dict[str, float | int]:
        try:
            information = soundfile.info(
                str(file_path)
            )

        except (
            RuntimeError,
            soundfile.LibsndfileError,
        ) as exception:
            raise InvalidFileError(
                "The uploaded file is not a valid or "
                "supported WAV audio file."
            ) from exception

        if information.format != "WAV":
            raise InvalidFileError(
                "The uploaded file is not encoded as WAV."
            )

        if information.samplerate <= 0:
            raise InvalidFileError(
                "The audio file has an invalid sample rate."
            )

        if information.channels <= 0:
            raise InvalidFileError(
                "The audio file has an invalid channel count."
            )

        if information.frames <= 0:
            raise InvalidFileError(
                "The audio file contains no audio frames."
            )

        duration_seconds = (
            information.frames / information.samplerate
        )

        if duration_seconds <= 0:
            raise InvalidFileError(
                "The audio file has an invalid duration."
            )

        return {
            "duration_seconds": round(
                duration_seconds,
                3,
            ),
            "sample_rate": information.samplerate,
            "channel_count": information.channels,
        }