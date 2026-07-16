from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

# Base 는 database.py 에서 정의한 것을 공유해야 create_all 이 테이블을 인식한다.
from app.database import Base


class Location(Base):
    """공공데이터 POI (TourAPI 4.0, 공공누리 3유형 — 내용 변경 금지, 읽기 전용)"""
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_id = Column(String, nullable=False, unique=True)
    content_type_id = Column(String, nullable=False)  # 12,14,15,25,28,32,38,39
    title = Column(String, nullable=False)
    addr1 = Column(String)
    addr2 = Column(String)
    tel = Column(String)
    mapx = Column(Float)   # 경도 (원본 string → float)
    mapy = Column(Float)   # 위도 (원본 string → float)
    cat1 = Column(String)
    cat2 = Column(String)
    cat3 = Column(String)
    first_image = Column(String)
    first_image2 = Column(String)
    created_time = Column(String)    # 원본 형식 유지 (YYYYMMDDHHmmss)
    modified_time = Column(String)
    district = Column(String)        # v1.1: addr1에서 추출한 구 이름 (파생 필드)
    likes = Column(Integer, nullable=False, default=0)  # v1.1: 좋아요 카운트
    event_start = Column(String)     # v1.2: 축제(15) 행사 시작일 YYYY-MM-DD (없으면 NULL)
    event_end = Column(String)       # v1.2: 축제(15) 행사 종료일 YYYY-MM-DD (없으면 NULL)

    __table_args__ = (
        Index("ix_locations_type", "content_type_id"),
        Index("ix_locations_title", "title"),
        Index("ix_locations_coords", "mapy", "mapx"),
        Index("ix_locations_type_district", "content_type_id", "district"),  # v1.1
    )


class Post(Base):
    """커뮤니티 게시글 (익명, 비밀번호 기반 수정·삭제)"""
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String, nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    password = Column(String, nullable=False)  # 평문 저장 — RFP 명시(교육 목적)
    views = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    comments = relationship(
        "Comment",
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="Comment.created_at",
    )

    __table_args__ = (
        Index("ix_posts_category_created", "category", "created_at"),
        Index("ix_posts_title", "title"),
    )


class Comment(Base):
    """게시글 댓글 (익명, 비밀번호 기반 수정·삭제 — 게시글과 동일 정책)"""
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    content = Column(Text, nullable=False)
    password = Column(String, nullable=False)  # 평문 저장 — 게시글과 동일(교육 목적)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    post = relationship("Post", back_populates="comments")

    __table_args__ = (
        Index("ix_comments_post_created", "post_id", "created_at"),
    )
