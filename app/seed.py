"""초기 데이터 시드 — data/*.json → SQLite (DB_SCHEMA_2.md §7)

실행: py -3.12 -m app.seed   (또는 python -m app.seed)

원칙
  - locations: content_id UNIQUE 로 INSERT OR IGNORE → 재실행 안전(멱등).
  - posts: 자연 유니크 키가 없어 테이블이 비어있을 때만 적재(중복 방지).
  - mapx/mapy: string→float 변환, 실패 시 NULL.
  - 빈 문자열("") → NULL 정규화.
  - district: 레코드에 있으면 사용, 없으면 addr1 에서 정규식 추출.
  - 실제 TourAPI 원본 키(contentid/firstimage/…)도 매핑 지원.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (create_all 이 모델을 인식하도록)
from app.database import Base, SessionLocal, engine
from app.models import Location, Post

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DISTRICT_RE = re.compile(r"서울특별시\s+(\S+구)")

# 쇼핑(38) 적재 여부 — 팀 결정 반영 (DB_SCHEMA §7.4).
# 실제 전체 데이터에선 쇼핑이 절반 이상이라 경량화 목적 제외를 검토하나,
# 목 데이터는 소량이라 데모 완결성을 위해 포함(True).
SEED_INCLUDE_SHOPPING = True


def _clean_str(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _to_float(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _pick(rec: dict, *keys):
    """여러 후보 키 중 먼저 값이 있는 것 반환 (snake_case ↔ TourAPI 원본 키 호환)."""
    for k in keys:
        v = rec.get(k)
        if v not in ("", None):
            return v
    return None


def _extract_district(rec: dict, addr1: str | None) -> str | None:
    given = _clean_str(_pick(rec, "district"))
    if given:
        return given
    if addr1:
        m = DISTRICT_RE.search(addr1)
        if m:
            return m.group(1)
    return None


def _parse_dt(value) -> datetime | None:
    s = _clean_str(value)
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def normalize_location(rec: dict) -> dict:
    addr1 = _clean_str(_pick(rec, "addr1"))
    likes = _pick(rec, "likes")
    return {
        "content_id": _clean_str(_pick(rec, "content_id", "contentid")),
        "content_type_id": _clean_str(_pick(rec, "content_type_id", "contenttypeid")),
        "title": _clean_str(_pick(rec, "title")),
        "addr1": addr1,
        "addr2": _clean_str(_pick(rec, "addr2")),
        "tel": _clean_str(_pick(rec, "tel")),
        "mapx": _to_float(_pick(rec, "mapx")),
        "mapy": _to_float(_pick(rec, "mapy")),
        "cat1": _clean_str(_pick(rec, "cat1")),
        "cat2": _clean_str(_pick(rec, "cat2")),
        "cat3": _clean_str(_pick(rec, "cat3")),
        "first_image": _clean_str(_pick(rec, "first_image", "firstimage")),
        "first_image2": _clean_str(_pick(rec, "first_image2", "firstimage2")),
        "created_time": _clean_str(_pick(rec, "created_time", "createdtime")),
        "modified_time": _clean_str(_pick(rec, "modified_time", "modifiedtime")),
        "district": _extract_district(rec, addr1),
        "likes": int(likes) if likes not in (None, "") else 0,
    }


def seed_locations(db: Session) -> int:
    path = DATA_DIR / "locations.json"
    records = json.loads(path.read_text(encoding="utf-8"))

    rows: list[dict] = []
    skipped_shopping = 0
    for rec in records:
        norm = normalize_location(rec)
        # NOT NULL 필수값 검증
        if not (norm["content_id"] and norm["content_type_id"] and norm["title"]):
            continue
        if not SEED_INCLUDE_SHOPPING and norm["content_type_id"] == "38":
            skipped_shopping += 1
            continue
        rows.append(norm)

    if rows:
        # INSERT OR IGNORE (content_id 충돌 시 무시) → 멱등 재실행
        stmt = sqlite_insert(Location).on_conflict_do_nothing(
            index_elements=["content_id"]
        )
        db.execute(stmt, rows)
        db.commit()
    if skipped_shopping:
        print(f"  (쇼핑 {skipped_shopping}건 적재 제외 — SEED_INCLUDE_SHOPPING=False)")
    return len(rows)


def seed_posts(db: Session) -> int:
    existing = db.scalar(select(func.count()).select_from(Post)) or 0
    if existing:
        print(f"  posts 이미 {existing}건 존재 → 건너뜀 (중복 방지)")
        return 0

    records = json.loads((DATA_DIR / "posts.json").read_text(encoding="utf-8"))
    objs = []
    for rec in records:
        created = _parse_dt(rec.get("created_at")) or datetime.utcnow()
        objs.append(
            Post(
                category=_clean_str(rec.get("category")),
                title=_clean_str(rec.get("title")),
                content=rec.get("content") or "",
                password=str(rec.get("password") or ""),
                views=int(rec.get("views") or 0),
                created_at=created,
                updated_at=_parse_dt(rec.get("updated_at")),
            )
        )
    db.add_all(objs)
    db.commit()
    return len(objs)


def print_district_distribution(db: Session) -> None:
    """시드 후 district 분포 검증 (오추출 여부 확인용)."""
    stmt = (
        select(Location.district, func.count())
        .group_by(Location.district)
        .order_by(func.count().desc())
    )
    print("[district 분포]")
    for district, cnt in db.execute(stmt).all():
        print(f"  {district or '(NULL)'}: {cnt}")


def run() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        n_loc = seed_locations(db)
        n_post = seed_posts(db)
        total_loc = db.scalar(select(func.count()).select_from(Location)) or 0
        total_post = db.scalar(select(func.count()).select_from(Post)) or 0
        print(f"locations 입력 {n_loc}건 → DB 총 {total_loc}건")
        print(f"posts 입력 {n_post}건 → DB 총 {total_post}건")
        print_district_distribution(db)
    finally:
        db.close()


if __name__ == "__main__":
    run()
