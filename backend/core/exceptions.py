class ApplicationError(Exception):
    """Base exception for expected application errors."""

    status_code: int = 500
    error_code: str = "application_error"

    def __init__(
        self,
        message: str,
    ) -> None:
        self.message = message
        super().__init__(message)


class ResourceNotFoundError(ApplicationError):
    """Raised when a requested resource does not exist."""

    status_code = 404
    error_code = "resource_not_found"


class ResourceConflictError(ApplicationError):
    """Raised when a request conflicts with existing data."""

    status_code = 409
    error_code = "resource_conflict"


class FileTooLargeError(ApplicationError):
    """Raised when an uploaded file exceeds its size limit."""

    status_code = 413
    error_code = "file_too_large"


class InvalidFileError(ApplicationError):
    """Raised when an uploaded file is invalid."""

    status_code = 422
    error_code = "invalid_file"


class InvalidUploadMetadataError(ApplicationError):
    """Raised when ESP32 upload metadata is invalid."""

    status_code = 422
    error_code = "invalid_upload_metadata"


class ProcessingError(ApplicationError):
    """Raised when recording processing fails."""

    status_code = 500
    error_code = "processing_error"
    

class DetectionNotFoundError(Exception):
    """
    Raised when a requested detection does not exist.
    """

    def __init__(
        self,
        detection_id: object,
    ) -> None:
        super().__init__(
            f"Detection '{detection_id}' was not found."
        )