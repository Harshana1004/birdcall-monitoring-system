from api.routes.detections import (
    router as detections_router,
)
from api.routes.devices import (
    router as devices_router,
)
from api.routes.recordings import (
    router as recordings_router,
)

__all__ = [
    "detections_router",
    "devices_router",
    "recordings_router",
]