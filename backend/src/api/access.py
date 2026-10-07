"""
What each signed-in user may see.

Admins see everything. A normal user sees:
  * devices they own, and every recording/detection from them;
  * shared devices (Device.is_shared) and their recordings and
    detections, read-only;
  * recordings they created themselves through manual analysis.

Anything else is reported as "not found" rather than "forbidden",
so other users' ids do not leak.
"""

import uuid

from sqlalchemy import (
    ColumnElement,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.core.exceptions import (
    DeviceNotFoundError,
    PermissionDeniedError,
    RecordingNotFoundError,
)
from src.models import (
    Device,
    Recording,
    User,
)


def visible_device_ids(
    user: User,
):
    """
    Subquery of the ids of devices `user` owns or that are shared.
    """

    return select(
        Device.id
    ).where(
        or_(
            Device.owner_id
            == user.id,
            Device.is_shared.is_(True),
        )
    )


def recording_visibility(
    user: User,
) -> ColumnElement[bool] | None:
    """
    WHERE condition limiting Recording rows to what `user` may see,
    or None for admins (no restriction).
    """

    if user.is_admin:
        return None

    return or_(
        Recording.device_id.in_(
            visible_device_ids(
                user
            )
        ),
        Recording.uploaded_by_user_id
        == user.id,
    )


def device_visibility(
    user: User,
) -> ColumnElement[bool] | None:
    """
    WHERE condition limiting Device rows to what `user` may see,
    or None for admins.
    """

    if user.is_admin:
        return None

    return or_(
        Device.owner_id
        == user.id,
        Device.is_shared.is_(True),
    )


def can_manage_device(
    user: User,
    device: Device,
) -> bool:
    return user.is_admin or (
        device.owner_id
        == user.id
    )


def can_see_device(
    user: User,
    device: Device,
) -> bool:
    return device.is_shared or can_manage_device(
        user,
        device,
    )


def can_modify_recording(
    user: User,
    recording: Recording,
    device: Device | None,
) -> bool:
    if user.is_admin:
        return True

    if recording.uploaded_by_user_id == user.id:
        return True

    return device is not None and (
        device.owner_id
        == user.id
    )


def can_see_recording(
    user: User,
    recording: Recording,
    device: Device | None,
) -> bool:
    return can_modify_recording(
        user,
        recording,
        device,
    ) or (
        device is not None
        and device.is_shared
    )


async def get_visible_device(
    session: AsyncSession,
    user: User,
    device_id: uuid.UUID,
) -> Device:
    device = await session.get(
        Device,
        device_id,
    )

    if device is None or not can_see_device(
        user,
        device,
    ):
        raise DeviceNotFoundError()

    return device


async def get_managed_device(
    session: AsyncSession,
    user: User,
    device_id: uuid.UUID,
) -> Device:
    """
    A device `user` may change (owner or admin). Viewers of a shared
    device get 403; anyone else gets "not found".
    """

    device = await get_visible_device(
        session,
        user,
        device_id,
    )

    if not can_manage_device(
        user,
        device,
    ):
        raise PermissionDeniedError(
            "This device is shared with you read-only."
        )

    return device


async def get_visible_recording(
    session: AsyncSession,
    user: User,
    recording_id: uuid.UUID,
    *,
    modify: bool = False,
) -> Recording:
    """
    A recording `user` may see; with modify=True, one they may also
    delete (shared-device viewers get 403).
    """

    recording = await session.get(
        Recording,
        recording_id,
    )

    if recording is None:
        raise RecordingNotFoundError(
            f"Recording '{recording_id}' was not found."
        )

    device = await session.get(
        Device,
        recording.device_id,
    )

    if not can_see_recording(
        user,
        recording,
        device,
    ):
        raise RecordingNotFoundError(
            f"Recording '{recording_id}' was not found."
        )

    if modify and not can_modify_recording(
        user,
        recording,
        device,
    ):
        raise PermissionDeniedError(
            "This recording is shared with you read-only."
        )

    return recording
