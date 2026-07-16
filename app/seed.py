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
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import bindparam, func, select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (create_all 이 모델을 인식하도록)
from app.database import Base, SessionLocal, engine
from app.models import Comment, Location, Post

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


FESTIVAL_YEAR = 2026


def _ensure_festival_date_columns(db: Session) -> None:
    """기존 DB(구 스키마)에 event_start/event_end 컬럼이 없으면 추가한다.

    create_all 은 신규 테이블만 만들고 기존 테이블을 ALTER 하지 않으므로,
    이미 만들어진 locations 테이블에는 직접 컬럼을 붙여준다(SQLite ADD COLUMN).
    """
    existing = {row[1] for row in db.execute(text("PRAGMA table_info(locations)"))}
    for col in ("event_start", "event_end"):
        if col not in existing:
            db.execute(text(f"ALTER TABLE locations ADD COLUMN {col} VARCHAR"))
    db.commit()


def _demo_festival_dates(content_id: str) -> tuple[str, str]:
    """content_id 기반 결정론적 데모 행사일(시작/종료, 포함).

    원본 TourAPI 목록에는 행사일이 없어 데모용으로 생성한다(멱등).
    2026년 안에서 시작일을 정하고 1~5일 기간을 부여.
    """
    h = int(hashlib.md5(content_id.encode("utf-8")).hexdigest(), 16)
    day_of_year = h % 365          # 0 ~ 364
    duration = (h // 365) % 5      # 0 ~ 4 → 1~5일
    start = date(FESTIVAL_YEAR, 1, 1) + timedelta(days=day_of_year)
    end = start + timedelta(days=duration)
    return start.isoformat(), end.isoformat()


def seed_festival_dates(db: Session) -> int:
    """축제(content_type_id=15) 행사일 더미 채우기 — 데모용.

    event_start 가 비어있는 축제만 대상. 결정론적이라 재실행해도 멱등.
    """
    rows = db.execute(
        select(Location.id, Location.content_id).where(
            Location.content_type_id == "15",
            Location.event_start.is_(None),
        )
    ).all()
    params = []
    for loc_id, content_id in rows:
        if not content_id:
            continue
        start, end = _demo_festival_dates(content_id)
        params.append({"b_id": loc_id, "b_start": start, "b_end": end})
    if not params:
        return 0
    tbl = Location.__table__
    stmt = (
        tbl.update()
        .where(tbl.c.id == bindparam("b_id"))
        .values(event_start=bindparam("b_start"), event_end=bindparam("b_end"))
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


DUMMY_COMMENTS = [
    "좋은 정보 감사합니다!",
    "저도 가봐야겠네요 👍",
    "지난주에 다녀왔는데 정말 좋았어요.",
    "혹시 주차는 편한가요?",
    "가격대가 어떻게 되는지 궁금해요.",
    "주말엔 사람이 많나요?",
    "대중교통으로 가기 편한가요?",
    "사진도 같이 올려주시면 좋을 것 같아요.",
    "근처에 다른 볼거리도 있을까요?",
    "정보 공유 고맙습니다 :)",
    "오 유용하네요. 저장해뒀어요.",
    "다음에 꼭 방문해봐야겠어요.",
    "영업시간 아시는 분 계신가요?",
    "완전 공감합니다!",
    "추천 감사해요, 참고할게요.",
]


def seed_comments(db: Session) -> int:
    """더미 댓글 — 데모용. 게시글마다 0~3개를 content_id(post.id) 기반 결정론적으로 생성.

    comments 가 하나라도 있으면 건너뜀(사용자 댓글/재실행 보호). 게시글과 동일하게
    비밀번호는 '1234', 작성일은 게시글 작성일 이후로 배치.
    """
    existing = db.scalar(select(func.count()).select_from(Comment)) or 0
    if existing:
        print(f"  comments 이미 {existing}건 존재 → 건너뜀")
        return 0

    posts = db.execute(select(Post.id, Post.created_at)).all()
    n_pool = len(DUMMY_COMMENTS)
    objs: list[Comment] = []
    for post_id, created in posts:
        h = int(hashlib.md5(f"comment-{post_id}".encode("utf-8")).hexdigest(), 16)
        count = h % 4  # 0~3개
        used: set[int] = set()
        base_dt = created or datetime.utcnow()
        for i in range(count):
            idx = (h // (n_pool ** i)) % n_pool
            while idx in used:  # 같은 글에 중복 문구 방지
                idx = (idx + 1) % n_pool
            used.add(idx)
            # 게시글 작성 이후 시간에 배치 (결정론적, 순차 증가)
            offset_h = ((h >> (i + 1)) % 60) + 1 + i * 20
            objs.append(
                Comment(
                    post_id=post_id,
                    content=DUMMY_COMMENTS[idx],
                    password="1234",
                    created_at=base_dt + timedelta(hours=offset_h),
                )
            )
    db.add_all(objs)
    db.commit()
    return len(objs)


def run() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _ensure_festival_date_columns(db)
        n_loc = seed_locations(db)
        n_likes = seed_location_likes(db)
        n_fest = seed_festival_dates(db)
        n_post = seed_posts(db)
        n_comment = seed_comments(db)
        total_loc = db.scalar(select(func.count()).select_from(Location)) or 0
        total_post = db.scalar(select(func.count()).select_from(Post)) or 0
        total_comment = db.scalar(select(func.count()).select_from(Comment)) or 0
        print(f"locations 입력 {n_loc}건 → DB 총 {total_loc}건")
        print(f"지역정보 추천수 더미 {n_likes}건 채움 (likes==0 대상)")
        print(f"축제 행사일 더미 {n_fest}건 채움 (event_start==NULL 대상)")
        print(f"posts 입력 {n_post}건 → DB 총 {total_post}건")
        print(f"comments 더미 {n_comment}건 입력 → DB 총 {total_comment}건")
        print_type_distribution(db)
        print_district_distribution(db)
    finally:
        db.close()


if __name__ == "__main__":
    run()
