"""대시보드 통계 스키마 — 자체 DB 집계 결과."""
from pydantic import BaseModel


class LabeledCount(BaseModel):
    code: str
    label: str
    count: int


class DistrictCount(BaseModel):
    district: str
    count: int


class TitleLikes(BaseModel):
    title: str
    likes: int


class MonthCount(BaseModel):
    month: str  # YYYY-MM
    count: int


class StatsTotals(BaseModel):
    locations: int
    posts: int
    festivals: int
    likes_sum: int


class StatsResponse(BaseModel):
    totals: StatsTotals
    locations_by_category: list[LabeledCount]
    locations_by_district: list[DistrictCount]
    top_liked: list[TitleLikes]
    posts_by_category: list[LabeledCount]
    festivals_by_month: list[MonthCount]
