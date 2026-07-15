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

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import bindparam, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (create_all 이 모델을 인식하도록)
from app.database import Base, SessionLocal, engine
from app.models import Location, Post

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEOUL_DIR = DATA_DIR / "서울"  # TourAPI 원본 JSON(파일별 = 콘텐츠 유형별)
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


def _load_items(path: Path) -> list[dict]:
    """TourAPI 원본 파일에서 items[] 추출. flat array 형태도 호환."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("items", [])
    if isinstance(data, list):
        return data
    return []


def seed_locations(db: Session) -> int:
    files = sorted(SEOUL_DIR.glob("*.json"))
    if not files:
        print(f"  경고: {SEOUL_DIR} 에 JSON 이 없습니다. locations 시드 건너뜀.")
        return 0

    rows: list[dict] = []
    skipped_shopping = 0
    skipped_invalid = 0
    for path in files:
        for rec in _load_items(path):
            norm = normalize_location(rec)
            # NOT NULL 필수값 검증 (content_id / content_type_id / title)
            if not (norm["content_id"] and norm["content_type_id"] and norm["title"]):
                skipped_invalid += 1
                continue
            if not SEED_INCLUDE_SHOPPING and norm["content_type_id"] == "38":
                skipped_shopping += 1
                continue
            rows.append(norm)

    if rows:
        # INSERT OR IGNORE (content_id 충돌 시 무시) → 멱등 재실행. 대량이라 청크 처리.
        stmt = sqlite_insert(Location).on_conflict_do_nothing(
            index_elements=["content_id"]
        )
        for i in range(0, len(rows), 1000):
            db.execute(stmt, rows[i : i + 1000])
        db.commit()
    if skipped_shopping:
        print(f"  (쇼핑 {skipped_shopping}건 적재 제외 — SEED_INCLUDE_SHOPPING=False)")
    if skipped_invalid:
        print(f"  (필수값 누락 {skipped_invalid}건 제외)")
    return len(rows)


def _dummy_like_count(content_id: str) -> int:
    """content_id 기반 결정론적 더미 추천수.

    - 재실행해도 같은 값(멱등) → 시드 반복 안전.
    - 롱테일 분포: 대부분 한 자릿수, 소수만 인기 장소로 높게.
    """
    h = int(hashlib.md5(content_id.encode("utf-8")).hexdigest(), 16)
    r = h % 1000
    if r < 550:
        return r % 15            # 0~14 (대부분)
    if r < 870:
        return 15 + (r % 85)     # 15~99
    if r < 970:
        return 100 + (r % 200)   # 100~299
    return 300 + (r % 500)       # 300~799 (소수 인기 장소)


def seed_location_likes(db: Session) -> int:
    """지역정보 추천수(likes) 더미 채우기 — 데모용.

    likes == 0 인 행만 결정론적 값으로 채운다. 사용자가 실제로 누른
    추천(likes > 0)은 건드리지 않으므로 운영 중 재실행해도 안전.
    """
    rows = db.execute(
        select(Location.id, Location.content_id).where(Location.likes == 0)
    ).all()
    params = [
        {"b_id": loc_id, "b_likes": _dummy_like_count(content_id)}
        for loc_id, content_id in rows
        if content_id
    ]
    if not params:
        return 0
    # ORM 엔티티(update(Location))는 PK 벌크 경로를 타서 executemany 가 막히므로
    # Core 테이블 업데이트로 executemany 수행.
    tbl = Location.__table__
    stmt = (
        tbl.update()
        .where(tbl.c.id == bindparam("b_id"))
        .values(likes=bindparam("b_likes"))
    )
    for i in range(0, len(params), 1000):
        db.execute(stmt, params[i : i + 1000])
    db.commit()
    return len(params)


def seed_posts(db: Session) -> int:
    # posts 는 커뮤니티(사용자 생성) 데이터라 원본 시드 소스가 없음.
    # 데모용 초기 게시글 파일(data/posts.json)이 있을 때만 적재, 없으면 빈 게시판으로 시작.
    posts_path = DATA_DIR / "posts.json"
    if not posts_path.exists():
        print("  posts 시드 파일 없음 → 빈 게시판으로 시작 (커뮤니티가 채움)")
        return 0

    existing = db.scalar(select(func.count()).select_from(Post)) or 0
    if existing:
        print(f"  posts 이미 {existing}건 존재 → 건너뜀 (중복 방지)")
        return 0

    records = json.loads(posts_path.read_text(encoding="utf-8"))
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


TYPE_LABELS = {
    "12": "관광지", "14": "문화시설", "15": "축제공연행사", "25": "여행코스",
    "28": "레포츠", "32": "숙박", "38": "쇼핑", "39": "음식점",
}


def print_type_distribution(db: Session) -> None:
    """시드 후 콘텐츠 유형별 건수."""
    stmt = (
        select(Location.content_type_id, func.count())
        .group_by(Location.content_type_id)
        .order_by(Location.content_type_id)
    )
    print("[유형별 분포]")
    for ctid, cnt in db.execute(stmt).all():
        print(f"  {ctid} {TYPE_LABELS.get(ctid, '?')}: {cnt}")


def print_district_distribution(db: Session) -> None:
    """시드 후 district 분포 검증 (오추출 여부 확인용). 상위 15개만."""
    stmt = (
        select(Location.district, func.count())
        .group_by(Location.district)
        .order_by(func.count().desc())
        .limit(15)
    )
    print("[district 분포 (상위 15)]")
    for district, cnt in db.execute(stmt).all():
        print(f"  {district or '(NULL)'}: {cnt}")


def run() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        n_loc = seed_locations(db)
        n_likes = seed_location_likes(db)
        n_post = seed_posts(db)
        total_loc = db.scalar(select(func.count()).select_from(Location)) or 0
        total_post = db.scalar(select(func.count()).select_from(Post)) or 0
        print(f"locations 입력 {n_loc}건 → DB 총 {total_loc}건")
        print(f"지역정보 추천수 더미 {n_likes}건 채움 (likes==0 대상)")
        print(f"posts 입력 {n_post}건 → DB 총 {total_post}건")
        print_type_distribution(db)
        print_district_distribution(db)
    finally:
        db.close()


if __name__ == "__main__":
    run()
