from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_CATEGORIES = {"12", "14", "15", "25", "28", "32", "38", "39"}


class PostCreate(BaseModel):
    category: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1)
    password: str = Field(..., min_length=4, max_length=20)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        if value not in VALID_CATEGORIES:
            raise ValueError("유효하지 않은 카테고리입니다.")
        return value


class PostUpdate(BaseModel):
    password: str = Field(..., min_length=4, max_length=20)
    category: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        if value not in VALID_CATEGORIES:
            raise ValueError("유효하지 않은 카테고리입니다.")
        return value


class PostVerifyRequest(BaseModel):
    password: str = Field(..., min_length=4, max_length=20)


class PostDeleteRequest(BaseModel):
    password: str = Field(..., min_length=4, max_length=20)


class PostListItem(BaseModel):
    id: int
    category: str
    title: str
    views: int
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class PostResponse(BaseModel):
    id: int
    category: str
    title: str
    content: str
    views: int
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class PostListResponse(BaseModel):
    items: list[PostListItem]
    total: int
    page: int
    size: int


class PostVerifyResponse(BaseModel):
    verified: bool
