import logging
import secrets
import uuid
from datetime import (
    datetime,
    timedelta,
    timezone,
)

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
)

from src.core.config import settings


logger = logging.getLogger(
    __name__
)


# ============================================================
# Secret hashing (passwords and device claim codes)
# ============================================================


# argon2id with the library's recommended parameters.
_hasher = PasswordHasher()

# Verified against when an email is unknown, so a failed login
# takes the same time whether or not the account exists.
_DUMMY_HASH = _hasher.hash(
    "dummy-password-for-timing"
)


def hash_secret(
    secret: str,
) -> str:
    return _hasher.hash(
        secret
    )


def verify_secret(
    secret_hash: str | None,
    secret: str,
) -> bool:
    """
    True if `secret` matches `secret_hash`. A missing hash still
    costs one verification, to keep timing uniform.
    """

    try:
        return _hasher.verify(
            secret_hash or _DUMMY_HASH,
            secret,
        ) and secret_hash is not None

    except (
        VerificationError,
        InvalidHashError,
    ):
        return False


def secret_needs_rehash(
    secret_hash: str,
) -> bool:
    return _hasher.check_needs_rehash(
        secret_hash
    )


# ============================================================
# Access tokens (JWT, HS256)
# ============================================================


_JWT_ALGORITHM = "HS256"

_jwt_secret = settings.jwt_secret_key

if not _jwt_secret:
    _jwt_secret = secrets.token_urlsafe(
        48
    )

    logger.warning(
        "JWT_SECRET_KEY is not set; using a random key. "
        "Login tokens will be invalid after a restart."
    )


def create_access_token(
    user_id: uuid.UUID,
) -> tuple[str, datetime]:
    """
    Return (token, expiry) for the given user.
    """

    issued_at = datetime.now(
        timezone.utc
    )

    expires_at = (
        issued_at
        + timedelta(
            minutes=(
                settings.access_token_expire_minutes
            )
        )
    )

    token = jwt.encode(
        {
            "sub": str(
                user_id
            ),
            "iat": issued_at,
            "exp": expires_at,
            "type": "access",
        },
        _jwt_secret,
        algorithm=_JWT_ALGORITHM,
    )

    return (
        token,
        expires_at,
    )


def decode_access_token(
    token: str,
) -> uuid.UUID | None:
    """
    The user id from a valid, unexpired token, else None.
    """

    try:
        payload = jwt.decode(
            token,
            _jwt_secret,
            algorithms=[
                _JWT_ALGORITHM
            ],
            options={
                "require": [
                    "sub",
                    "exp",
                ],
            },
        )

        if payload.get(
            "type"
        ) != "access":
            return None

        return uuid.UUID(
            payload["sub"]
        )

    except (
        jwt.PyJWTError,
        ValueError,
    ):
        return None


# ============================================================
# Device claim codes
# ============================================================


# No 0/O or 1/I, so codes printed on a device are easy to read.
_CLAIM_ALPHABET = (
    "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
)

_CLAIM_GROUPS = 3
_CLAIM_GROUP_LENGTH = 4


def generate_claim_code() -> str:
    """
    A random claim code such as "K7QM-3XRP-W9TD" (60 bits).
    """

    groups = [
        "".join(
            secrets.choice(
                _CLAIM_ALPHABET
            )
            for _ in range(
                _CLAIM_GROUP_LENGTH
            )
        )
        for _ in range(
            _CLAIM_GROUPS
        )
    ]

    return "-".join(
        groups
    )


def normalize_claim_code(
    code: str,
) -> str:
    """
    Upper-case and drop spaces/hyphens, so "k7qm 3xrp-w9td" and
    "K7QM-3XRP-W9TD" are the same code.
    """

    return "".join(
        character
        for character in code.upper()
        if character.isalnum()
    )
