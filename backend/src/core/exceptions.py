class ApplicationError(Exception):
    """
    Base class for expected application errors.
    """

    status_code: int = 500
    error_code: str = "application_error"
    default_message: str = (
        "An application error occurred."
    )

    def __init__(
        self,
        message: str | None = None,
    ) -> None:
        self.message = (
            message
            if message is not None
            else self.default_message
        )

        super().__init__(
            self.message
        )


# ============================================================
# Devices
# ============================================================


class DeviceNotFoundError(
    ApplicationError
):
    status_code = 404
    error_code = "device_not_found"
    default_message = "Device not found."


class DuplicateDeviceCodeError(
    ApplicationError
):
    status_code = 409
    error_code = "duplicate_device_code"
    default_message = (
        "A device with this device code already exists."
    )


class InactiveDeviceError(
    ApplicationError
):
    status_code = 409
    error_code = "inactive_device"
    default_message = (
        "ROI snippets cannot be uploaded for an inactive device."
    )


# ============================================================
# Recordings
# ============================================================


class RecordingNotFoundError(
    ApplicationError
):
    status_code = 404
    error_code = "recording_not_found"
    default_message = "Recording not found."


class RecordingConflictError(
    ApplicationError
):
    status_code = 409
    error_code = "recording_conflict"
    default_message = (
        "The recording conflicts with an existing recording."
    )


class InvalidUploadMetadataError(
    ApplicationError
):
    status_code = 422
    error_code = "invalid_upload_metadata"
    default_message = (
        "Invalid recording upload metadata."
    )


# ============================================================
# Audio files
# ============================================================


class InvalidAudioFileError(
    ApplicationError
):
    status_code = 422
    error_code = "invalid_audio_file"
    default_message = (
        "The uploaded audio file is invalid."
    )


class AudioFileTooLargeError(
    ApplicationError
):
    status_code = 413
    error_code = "audio_file_too_large"
    default_message = (
        "The uploaded audio file is too large."
    )


# ============================================================
# Detections
# ============================================================


class DetectionNotFoundError(
    ApplicationError
):
    status_code = 404
    error_code = "detection_not_found"
    default_message = "Detection not found."


# ============================================================
# Processing
# ============================================================


class ProcessingError(
    ApplicationError
):
    status_code = 500
    error_code = "processing_error"
    default_message = (
        "Audio processing failed."
    )