"""댓글(comments) 라우터 — 게시글과 동일한 비밀번호 기반 CRUD.

  - GET    /api/posts/{post_id}/comments   목록
  - POST   /api/posts/{post_id}/comments   작성
  - POST   /api/comments/{comment_id}/verify  비밀번호 확인(수정 진입)
  - PUT    /api/comments/{comment_id}       수정
  - DELETE /api/comments/{comment_id}       삭제
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api", tags=["comments"])

POST_NOT_FOUND = "게시글을 찾을 수 없습니다."
COMMENT_NOT_FOUND = "댓글을 찾을 수 없습니다."
PASSWORD_MISMATCH = "비밀번호가 일치하지 않습니다."


def _get_post_or_404(post_id: int, db: Session) -> models.Post:
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail=POST_NOT_FOUND)
    return post


def _get_comment_or_404(comment_id: int, db: Session) -> models.Comment:
    comment = (
        db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    )
    if not comment:
        raise HTTPException(status_code=404, detail=COMMENT_NOT_FOUND)
    return comment


@router.get(
    "/posts/{post_id}/comments", response_model=schemas.CommentListResponse
)
def list_comments(post_id: int, db: Session = Depends(get_db)):
    _get_post_or_404(post_id, db)
    comments = (
        db.query(models.Comment)
        .filter(models.Comment.post_id == post_id)
        .order_by(models.Comment.created_at.asc())
        .all()
    )
    return {"items": comments, "total": len(comments)}


@router.post(
    "/posts/{post_id}/comments",
    response_model=schemas.CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    post_id: int,
    payload: schemas.CommentCreate,
    db: Session = Depends(get_db),
):
    _get_post_or_404(post_id, db)
    comment = models.Comment(post_id=post_id, **payload.model_dump())
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@router.post(
    "/comments/{comment_id}/verify",
    response_model=schemas.CommentVerifyResponse,
)
def verify_comment_password(
    comment_id: int,
    payload: schemas.CommentVerifyRequest,
    db: Session = Depends(get_db),
):
    comment = _get_comment_or_404(comment_id, db)
    if comment.password != payload.password:
        raise HTTPException(status_code=403, detail=PASSWORD_MISMATCH)
    return {"verified": True}


@router.put("/comments/{comment_id}", response_model=schemas.CommentResponse)
def update_comment(
    comment_id: int,
    payload: schemas.CommentUpdate,
    db: Session = Depends(get_db),
):
    comment = _get_comment_or_404(comment_id, db)
    if comment.password != payload.password:
        raise HTTPException(status_code=403, detail=PASSWORD_MISMATCH)
    comment.content = payload.content
    db.commit()
    db.refresh(comment)
    return comment


@router.delete(
    "/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_comment(
    comment_id: int,
    payload: schemas.CommentDeleteRequest,
    db: Session = Depends(get_db),
):
    comment = _get_comment_or_404(comment_id, db)
    if comment.password != payload.password:
        raise HTTPException(status_code=403, detail=PASSWORD_MISMATCH)
    db.delete(comment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
