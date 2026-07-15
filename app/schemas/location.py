"""지역정보(locations) Pydantic 스키마 — API_CONTRACT_2.md §2"""
from pydantic import BaseModel, ConfigDict


class LocationListItem(BaseModel):
    """§2-1 목록 아이템 (단건 상세는 v1.2 스코프 제외 → addr2/cat 제외)"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    content_id: str | None
    content_type_id: str
    title: str
    addr1: str | None
    district: str | None
    tel: str | None
    first_image: str | None
    first_image2: str | None
    mapx: float | None
    mapy: float | None
    likes: int
    event_start: str | None = None  # 축제(15) 행사 시작일 YYYY-MM-DD
    event_end: str | None = None    # 축제(15) 행사 종료일 YYYY-MM-DD


class LocationListResponse(BaseModel):
    items: list[LocationListItem]
    total: int
    page: int
    size: int


class MapPin(BaseModel):
    """§2-2 지도 핀 경량 아이템"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    content_type_id: str
    title: str
    mapx: float | None
    mapy: float | None


class MapResponse(BaseModel):
    items: list[MapPin]
    total: int


class LikeResponse(BaseModel):
    """§2-4 좋아요"""
    id: int
    likes: int


class DistrictListResponse(BaseModel):
    """§2-5 구 목록 ("전체"는 프론트가 추가 → 응답에 미포함)"""
    items: list[str]
