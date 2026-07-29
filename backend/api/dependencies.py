from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db


DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db),
]


PageNumber = Annotated[
    int,
    Query(
        ge=1,
        description="Page number starting from one.",
    ),
]


PageSize = Annotated[
    int,
    Query(
        ge=1,
        le=100,
        description="Number of records returned per page.",
    ),
]