import asyncio
import math
import uuid
from datetime import (
    datetime,
    timezone,
)
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    status,
)
from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.exc import (
    IntegrityError,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.api.auth import (
    AdminUser,
    CurrentUser,
)
from src.api.schemas import (
    ErrorResponse,
    LoginRequest,
    PaginatedResponse,
    PaginationMetadata,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    TokenResponse,
    UserAdminUpdate,
    UserResponse,
)
from src.core.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    PermissionDeniedError,
    UserNotFoundError,
)
from src.core.security import (
    create_access_token,
    hash_secret,
    secret_needs_rehash,
    verify_secret,
)
from src.database import get_db
from src.models import User


DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db),
]


auth_router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)

users_router = APIRouter(
    prefix="/api/v1/users",
    tags=["Users (admin)"],
)


# ============================================================
# Helpers
# ============================================================


def _token_response(
    user: User,
) -> TokenResponse:
    token, expires_at = create_access_token(
        user.id
    )

    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        user=UserResponse.model_validate(
            user
        ),
    )


async def _admin_count(
    session: AsyncSession,
) -> int:
    return (
        await session.scalar(
            select(
                func.count(
                    User.id
                )
            ).where(
                User.is_admin.is_(True),
                User.is_active.is_(True),
            )
        )
    ) or 0


# ============================================================
# Register / login
# ============================================================


@auth_router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {
            "model": ErrorResponse,
            "description": "Email already registered.",
        },
    },
)
async def register(
    data: RegisterRequest,
    session: DatabaseSession,
) -> TokenResponse:
    """
    Create an account and sign in. The very first account becomes
    an admin.
    """

    email = data.email.lower()

    if await session.scalar(
        select(User.id).where(
            User.email == email
        )
    ):
        raise EmailAlreadyRegisteredError()

    is_first_user = (
        (
            await session.scalar(
                select(
                    func.count(
                        User.id
                    )
                )
            )
        )
        or 0
    ) == 0

    password_hash = await asyncio.to_thread(
        hash_secret,
        data.password,
    )

    user = User(
        email=email,
        password_hash=password_hash,
        display_name=data.display_name,
        is_admin=is_first_user,
        last_login_at=datetime.now(
            timezone.utc
        ),
    )

    session.add(
        user
    )

    try:
        await session.commit()

    except IntegrityError as exception:
        await session.rollback()
        raise EmailAlreadyRegisteredError() from exception

    await session.refresh(
        user
    )

    return _token_response(
        user
    )


@auth_router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Incorrect email or password.",
        },
    },
)
async def login(
    data: LoginRequest,
    session: DatabaseSession,
) -> TokenResponse:
    user = await session.scalar(
        select(User).where(
            User.email == data.email.lower()
        )
    )

    # Always run one argon2 verification, so the response time does
    # not reveal whether the email exists.
    password_ok = await asyncio.to_thread(
        verify_secret,
        user.password_hash if user else None,
        data.password,
    )

    if user is None or not password_ok or not user.is_active:
        raise InvalidCredentialsError()

    if secret_needs_rehash(
        user.password_hash
    ):
        user.password_hash = await asyncio.to_thread(
            hash_secret,
            data.password,
        )

    user.last_login_at = datetime.now(
        timezone.utc
    )

    await session.commit()
    await session.refresh(
        user
    )

    return _token_response(
        user
    )


# ============================================================
# Current user
# ============================================================


@auth_router.get(
    "/me",
    response_model=UserResponse,
)
async def get_me(
    user: CurrentUser,
) -> UserResponse:
    return UserResponse.model_validate(
        user
    )


@auth_router.patch(
    "/me",
    response_model=UserResponse,
)
async def update_me(
    data: ProfileUpdateRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> UserResponse:
    if "display_name" in data.model_fields_set:
        name = (data.display_name or "").strip()
        user.display_name = name or None

    await session.commit()
    await session.refresh(
        user
    )

    return UserResponse.model_validate(
        user
    )


@auth_router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Current password is wrong.",
        },
    },
)
async def change_password(
    data: PasswordChangeRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> None:
    password_ok = await asyncio.to_thread(
        verify_secret,
        user.password_hash,
        data.current_password,
    )

    if not password_ok:
        raise InvalidCredentialsError(
            "Your current password is incorrect."
        )

    user.password_hash = await asyncio.to_thread(
        hash_secret,
        data.new_password,
    )

    await session.commit()


# ============================================================
# User management (admin)
# ============================================================


@users_router.get(
    "",
    response_model=PaginatedResponse[
        UserResponse
    ],
)
async def list_users(
    admin: AdminUser,
    session: DatabaseSession,
    page: Annotated[
        int,
        Query(ge=1),
    ] = 1,
    page_size: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 50,
    search: Annotated[
        str | None,
        Query(min_length=1, max_length=120),
    ] = None,
) -> PaginatedResponse[
    UserResponse
]:
    conditions = []

    if search and search.strip():
        pattern = f"%{search.strip()}%"
        conditions.append(
            or_(
                User.email.ilike(pattern),
                User.display_name.ilike(pattern),
            )
        )

    total_items = (
        await session.scalar(
            select(
                func.count(
                    User.id
                )
            ).where(
                *conditions
            )
        )
    ) or 0

    result = await session.execute(
        select(User)
        .where(*conditions)
        .order_by(
            User.created_at.asc()
        )
        .offset(
            (page - 1) * page_size
        )
        .limit(
            page_size
        )
    )

    return PaginatedResponse[
        UserResponse
    ](
        items=[
            UserResponse.model_validate(
                user
            )
            for user in result.scalars().all()
        ],
        pagination=PaginationMetadata(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=(
                math.ceil(
                    total_items / page_size
                )
                if total_items
                else 0
            ),
        ),
    )


@users_router.patch(
    "/{user_id}",
    response_model=UserResponse,
)
async def update_user(
    user_id: uuid.UUID,
    data: UserAdminUpdate,
    admin: AdminUser,
    session: DatabaseSession,
) -> UserResponse:
    user = await session.get(
        User,
        user_id,
    )

    if user is None:
        raise UserNotFoundError()

    removes_admin = (
        user.is_admin
        and user.is_active
        and (
            data.is_admin is False
            or data.is_active is False
        )
    )

    # Never leave the system without an active admin.
    if removes_admin and await _admin_count(
        session
    ) <= 1:
        raise PermissionDeniedError(
            "At least one active admin must remain."
        )

    if data.is_admin is not None:
        user.is_admin = data.is_admin

    if data.is_active is not None:
        user.is_active = data.is_active

    await session.commit()
    await session.refresh(
        user
    )

    return UserResponse.model_validate(
        user
    )
