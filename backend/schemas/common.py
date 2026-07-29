from typing import Generic, TypeVar

from pydantic import BaseModel, Field


DataType = TypeVar("DataType")


class ErrorResponse(BaseModel):
    error: str
    message: str


class PaginationMetadata(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedResponse(BaseModel, Generic[DataType]):
    items: list[DataType]
    pagination: PaginationMetadata