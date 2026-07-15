"""대시보드 통계 라우터 — 자체 DB 집계 (Chart.js 대시보드용).

  - GET /api/stats  대시보드 한 방 집계
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Location, Post
from app.schemas.stats import (
    DistrictCount,
    LabeledCount,
    MonthCount,
    StatsResponse,
    StatsTotals,
    TitleLikes,
)

router = APIRouter(prefix="/api/stats", tags=["stats"])

CATEGORY_LABELS = {
    "12": "관광지", "14": "문화시설", "15": "축제공연행사", "25": "여행코스",
    "28": "레포츠", "32": "숙박", "38": "쇼핑", "39": "음식점",
}

MONTH = func.substr(Location.event_start, 1, 7)


@router.get("", response_model=StatsResponse)
def dashboard_stats(db: Session = Depends(get_db)) -> StatsResponse:
    # 카테고리별 장소 수 (많은 순)
    loc_cat = db.execute(
        select(Location.content_type_id, func.count()).group_by(
            Location.content_type_id
        )
    ).all()
    locations_by_category = [
        LabeledCount(code=code, label=CATEGORY_LABELS.get(code, code), count=cnt)
        for code, cnt in sorted(loc_cat, key=lambda r: r[1], reverse=True)
    ]

    # 구별 장소 분포 Top 10
    dist = db.execute(
        select(Location.district, func.count())
        .where(Location.district.is_not(None))
        .group_by(Location.district)
        .order_by(func.count().desc())
        .limit(10)
    ).all()
    locations_by_district = [DistrictCount(district=d, count=c) for d, c in dist]

    # 추천 Top 10 장소
    liked = db.execute(
        select(Location.title, Location.likes)
        .order_by(Location.likes.desc(), Location.title.asc())
        .limit(10)
    ).all()
    top_liked = [TitleLikes(title=t, likes=lk) for t, lk in liked]

    # 커뮤니티 카테고리별 게시글 수 (많은 순)
    post_cat = db.execute(
        select(Post.category, func.count()).group_by(Post.category)
    ).all()
    posts_by_category = [
        LabeledCount(code=code, label=CATEGORY_LABELS.get(code, code), count=cnt)
        for code, cnt in sorted(post_cat, key=lambda r: r[1], reverse=True)
    ]

    # 축제 월별 건수 (event_start 기준)
    fest = db.execute(
        select(MONTH, func.count())
        .where(Location.content_type_id == "15", Location.event_start.is_not(None))
        .group_by(MONTH)
        .order_by(MONTH)
    ).all()
    festivals_by_month = [MonthCount(month=m, count=c) for m, c in fest]

    totals = StatsTotals(
        locations=db.scalar(select(func.count()).select_from(Location)) or 0,
        posts=db.scalar(select(func.count()).select_from(Post)) or 0,
        festivals=db.scalar(
            select(func.count())
            .select_from(Location)
            .where(Location.content_type_id == "15")
        )
        or 0,
        likes_sum=db.scalar(select(func.coalesce(func.sum(Location.likes), 0))) or 0,
    )

    return StatsResponse(
        totals=totals,
        locations_by_category=locations_by_category,
        locations_by_district=locations_by_district,
        top_liked=top_liked,
        posts_by_category=posts_by_category,
        festivals_by_month=festivals_by_month,
    )
