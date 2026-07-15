"""지역정보 (locations) 라우터 — 담당: B(목록)·C(지도) / 백엔드

API_CONTRACT_2.md §2.
  - GET  /api/locations              §2-1 목록 (type/q/district/sort/page/size)
  - GET  /api/locations/map          §2-2 지도 핀 경량 (types/limit)
  - GET  /api/locations/districts    §2-5 구 목록
  - POST /api/locations/{id}/like    §2-4 좋아요 +1
  - POST /api/locations/{id}/unlike  §2-4 좋아요 취소 -1
  ※ 2-3 단건 조회는 v1.2 스코프 제외 — 구현하지 않음.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Location
from app.schemas.location import (
    DistrictListResponse,
    LikeResponse,
    LocationListItem,
    LocationListResponse,
    MapPin,
    MapResponse,
)

router = APIRouter(prefix="/api/locations", tags=["locations"])

MAP_LIMIT_DEFAULT = 500
MAP_LIMIT_MAX = 2000


@router.get("", response_model=LocationListResponse)
def list_locations(
    type: str | None = Query(
        None,
        description="contentTypeId (12/14/15/25/28/32/38/39). 미지정 시 전체 카테고리",
    ),
    q: str | None = Query(None, description="장소명(title) 검색"),
    district: str | None = Query(None, description="구별 필터 (예: 종로구)"),
    sort: str = Query("name", pattern="^(name|likes)$"),
    page: int = Query(1, ge=1),
    size: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
) -> LocationListResponse:
    conditions = []
    if type:
        conditions.append(Location.content_type_id == type)
    if q:
        conditions.append(Location.title.like(f"%{q}%"))
    if district:
        conditions.append(Location.district == district)

    count_stmt = select(func.count()).select_from(Location)
    stmt = select(Location)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
        stmt = stmt.where(*conditions)

    total = db.scalar(count_stmt)
    if sort == "likes":
        # 추천순, 동률 시 이름(가나다)순 2차 정렬
        stmt = stmt.order_by(Location.likes.desc(), Location.title.asc())
    else:
        stmt = stmt.order_by(Location.title.asc())
    stmt = stmt.offset((page - 1) * size).limit(size)

    rows = db.execute(stmt).scalars().all()
    items = [LocationListItem.model_validate(r) for r in rows]
    return LocationListResponse(items=items, total=total or 0, page=page, size=size)


@router.get("/map", response_model=MapResponse)
def map_pins(
    types: str | None = Query(
        None, description="콤마 구분 content_type_id 목록 (예: 12,39)"
    ),
    district: str | None = Query(
        None, description="구별 필터 (예: 종로구). 미지정 시 전체 구"
    ),
    limit: int = Query(MAP_LIMIT_DEFAULT, ge=1, le=MAP_LIMIT_MAX),
    db: Session = Depends(get_db),
) -> MapResponse:
    # 좌표 있는 항목만 (지도 핀)
    stmt = select(Location).where(
        Location.mapx.is_not(None), Location.mapy.is_not(None)
    )
    if types:
        type_list = [t.strip() for t in types.split(",") if t.strip()]
        if type_list:
            stmt = stmt.where(Location.content_type_id.in_(type_list))
    if district:
        stmt = stmt.where(Location.district == district)
    stmt = stmt.limit(limit)

    rows = db.execute(stmt).scalars().all()
    items = [MapPin.model_validate(r) for r in rows]
    return MapResponse(items=items, total=len(items))


@router.get("/districts", response_model=DistrictListResponse)
def list_districts(
    type: str | None = Query(None, description="지정 시 해당 타입의 구만 반환"),
    db: Session = Depends(get_db),
) -> DistrictListResponse:
    stmt = select(Location.district).where(Location.district.is_not(None))
    if type:
        stmt = stmt.where(Location.content_type_id == type)
    stmt = stmt.distinct().order_by(Location.district.asc())
    items = [row[0] for row in db.execute(stmt).all()]
    return DistrictListResponse(items=items)


@router.post("/{location_id}/like", response_model=LikeResponse)
def like_location(
    location_id: int, db: Session = Depends(get_db)
) -> LikeResponse:
    loc = db.get(Location, location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="장소를 찾을 수 없습니다.")
    # 익명 서비스 — 단순 카운트 증가 (계정 기반 중복 방지 없음, 스코프 외)
    loc.likes = (loc.likes or 0) + 1
    db.commit()
    db.refresh(loc)
    return LikeResponse(id=loc.id, likes=loc.likes)


@router.post("/{location_id}/unlike", response_model=LikeResponse)
def unlike_location(
    location_id: int, db: Session = Depends(get_db)
) -> LikeResponse:
    loc = db.get(Location, location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="장소를 찾을 수 없습니다.")
    # 좋아요 취소 — 카운트 감소 (0 미만으로 내려가지 않도록 방어)
    loc.likes = max(0, (loc.likes or 0) - 1)
    db.commit()
    db.refresh(loc)
    return LikeResponse(id=loc.id, likes=loc.likes)
