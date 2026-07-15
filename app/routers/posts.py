from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(
    prefix="/api/posts",
    tags=["posts"],
)


@router.get("", response_model=schemas.PostListResponse)
def get_posts(
    category: str | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
):
    query = db.query(models.Post)

    if category:
        query = query.filter(models.Post.category == category)
    if q:
        query = query.filter(models.Post.title.contains(q))

    total = query.count()
    posts = (
        query.order_by(models.Post.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return {
        "items": posts,
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/{post_id}", response_model=schemas.PostResponse)
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    post.views += 1
    db.commit()
    db.refresh(post)

    return post


@router.post(
    "",
    response_model=schemas.PostResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_post(
    post_data: schemas.PostCreate,
    db: Session = Depends(get_db),
):
    post = models.Post(**post_data.model_dump())

    db.add(post)
    db.commit()
    db.refresh(post)

    return post


@router.post("/{post_id}/verify", response_model=schemas.PostVerifyResponse)
def verify_post_password(
    post_id: int,
    payload: schemas.PostVerifyRequest,
    db: Session = Depends(get_db),
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    if post.password != payload.password:
        raise HTTPException(status_code=403, detail="비밀번호가 일치하지 않습니다.")

    return {"verified": True}


@router.put("/{post_id}", response_model=schemas.PostResponse)
def update_post(
    post_id: int,
    payload: schemas.PostUpdate,
    db: Session = Depends(get_db),
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    if post.password != payload.password:
        raise HTTPException(status_code=403, detail="비밀번호가 일치하지 않습니다.")

    post.category = payload.category
    post.title = payload.title
    post.content = payload.content

    db.commit()
    db.refresh(post)

    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: int,
    payload: schemas.PostDeleteRequest,
    db: Session = Depends(get_db),
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    if post.password != payload.password:
        raise HTTPException(status_code=403, detail="비밀번호가 일치하지 않습니다.")

    db.delete(post)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)