"""
What each signed-in user may see.

Admins see everything. A normal user sees:
  * devices they own, and every recording/detection from them;
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
    RecordingNotFoundError,
)
from src.models import (
    Device,
    Recording,
    User,
)


def owned_device_ids(
    user: User,
):
    """
    Subquery of the ids of devices owned by `user`.
    """

    return select(
        Device.id
    ).where(
        Device.owner_id
        == user.id
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
            owned_device_ids(
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

    return (
        Device.owner_id
        == user.id
    )


def can_manage_device(
    user: User,
    device: Device,
) -> bool:
    return user.is_admin or (
        device.owner_id
        == user.id
    )


def can_see_recording(
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


async def get_visible_device(
    session: AsyncSession,
    user: User,
    device_id: uuid.UUID,
) -> Device:
    device = await session.get(
        Device,
        device_id,
    )

    if device is None or not can_manage_device(
        user,
        device,
    ):
        raise DeviceNotFoundError()

    return device


async def get_visible_recording(
    session: AsyncSession,
    user: User,
    recording_id: uuid.UUID,
) -> Recording:
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

    return recording
