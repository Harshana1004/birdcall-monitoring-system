from src.api.detections import (
    router as detections_router,
)
from src.api.devices import (
    router as devices_router,
)
from src.api.recordings import (
    router as recordings_router,
)


__all__ = [
    "devices_router",
    "recordings_router",
    "detections_router",
]