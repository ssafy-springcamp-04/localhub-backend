"""Pydantic 스키마 패키지.

posts.py 가 `from .. import schemas; schemas.PostCreate` 형태로 접근하므로
post 스키마를 패키지 레벨로 재수출한다. (location 스키마는 별도 모듈에서 직접 import)
"""
from app.schemas.comment import (
    CommentCreate,
    CommentDeleteRequest,
    CommentListResponse,
    CommentResponse,
    CommentUpdate,
    CommentVerifyRequest,
    CommentVerifyResponse,
)
from app.schemas.post import (
    PostCreate,
    PostDeleteRequest,
    PostListItem,
    PostListResponse,
    PostResponse,
    PostUpdate,
    PostVerifyRequest,
    PostVerifyResponse,
)

__all__ = [
    "PostCreate",
    "PostUpdate",
    "PostVerifyRequest",
    "PostDeleteRequest",
    "PostListItem",
    "PostResponse",
    "PostListResponse",
    "PostVerifyResponse",
    "CommentCreate",
    "CommentUpdate",
    "CommentVerifyRequest",
    "CommentDeleteRequest",
    "CommentResponse",
    "CommentListResponse",
    "CommentVerifyResponse",
]
