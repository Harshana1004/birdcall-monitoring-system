import secrets
from typing import Annotated

from fastapi import (
    Depends,
    Header,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.core.config import settings
from src.core.exceptions import (
    AuthenticationError,
    DeviceAuthenticationError,
    PermissionDeniedError,
)
from src.core.security import (
    decode_access_token,
)
from src.database import get_db
from src.models import User


# ============================================================
# Device API key
# ============================================================


DEVICE_KEY_HEADER = (
    "X-Device-Key"
)


def require_device_key(
    x_device_key: Annotated[
        str | None,
        Header(
            alias=DEVICE_KEY_HEADER,
            description=(
                "Shared device API key (DEVICE_API_KEY on the "
                "server)."
            ),
        ),
    ] = None,
) -> None:
    """
    Reject device uploads that do not carry the configured key.

    When DEVICE_API_KEY is not set the check is skipped, so local
    development keeps working without a key.
    """

    expected_key = (
        settings.device_api_key
    )

    if not expected_key:
        return

    if x_device_key is None or not secrets.compare_digest(
        x_device_key.encode(
            "utf-8"
        ),
        expected_key.encode(
            "utf-8"
        ),
    ):
        raise DeviceAuthenticationError()


# ============================================================
# Signed-in users (Authorization: Bearer <access token>)
# ============================================================


_bearer_scheme = HTTPBearer(
    auto_error=False,
    description=(
        "Access token from POST /api/v1/auth/login."
    ),
)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(
            _bearer_scheme
        ),
    ],
    session: Annotated[
        AsyncSession,
        Depends(
            get_db
        ),
    ],
) -> User:
    """
    The active user identified by the bearer token, else 401.
    """

    if credentials is None:
        raise AuthenticationError()

    user_id = decode_access_token(
        credentials.credentials
    )

    if user_id is None:
        raise AuthenticationError(
            "Your session has expired. Please sign in again."
        )

    user = await session.get(
        User,
        user_id,
    )

    if user is None or not user.is_active:
        raise AuthenticationError(
            "Your session has expired. Please sign in again."
        )

    return user


CurrentUser = Annotated[
    User,
    Depends(
        get_current_user
    ),
]


async def require_admin(
    user: CurrentUser,
) -> User:
    if not user.is_admin:
        raise PermissionDeniedError()

    return user


AdminUser = Annotated[
    User,
    Depends(
        require_admin
    ),
]
