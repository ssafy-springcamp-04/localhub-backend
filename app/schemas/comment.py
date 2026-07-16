"""댓글(comments) Pydantic 스키마 — 게시글과 동일한 비밀번호 기반 정책."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)
    password: str = Field(..., min_length=4, max_length=20)


class CommentUpdate(BaseModel):
    password: str = Field(..., min_length=4, max_length=20)
    content: str = Field(..., min_length=1, max_length=500)


class CommentVerifyRequest(BaseModel):
    password: str = Field(..., min_length=4, max_length=20)


class CommentDeleteRequest(BaseModel):
    password: str = Field(..., min_length=4, max_length=20)


class CommentResponse(BaseModel):
    id: int
    post_id: int
    content: str
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CommentListResponse(BaseModel):
    items: list[CommentResponse]
    total: int


class CommentVerifyResponse(BaseModel):
    verified: bool
