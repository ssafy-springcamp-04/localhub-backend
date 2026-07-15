"""지역정보(locations) · 좋아요 · 통계(stats) API 테스트.

기존 test_posts_api 와 get_db 오버라이드가 충돌하지 않도록,
픽스처에서 오버라이드를 설정하고 테스트 후 원복한다.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Location, Post

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _seed(db):
    db.add_all(
        [
            Location(id=1, content_id="c1", content_type_id="12", title="경복궁",
                     district="종로구", likes=10, mapx=126.97, mapy=37.57),
            Location(id=2, content_id="c2", content_type_id="12", title="남산타워",
                     district="용산구", likes=5),
            Location(id=3, content_id="c3", content_type_id="15", title="서울축제",
                     district="중구", likes=3,
                     event_start="2026-05-01", event_end="2026-05-03"),
            Location(id=4, content_id="c4", content_type_id="38", title="광장시장",
                     district="종로구", likes=0),
        ]
    )
    db.add_all(
        [
            Post(category="12", title="관광 글1", content="a", password="1234"),
            Post(category="12", title="관광 글2", content="b", password="1234"),
            Post(category="15", title="축제 글", content="c", password="1234"),
        ]
    )
    db.commit()


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        _seed(db)
    finally:
        db.close()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        if prev is not None:
            app.dependency_overrides[get_db] = prev
        else:
            app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine)


# ---- 목록 조회 -------------------------------------------------------------

def test_list_by_type(client):
    res = client.get("/api/locations", params={"type": "12"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    titles = {it["title"] for it in data["items"]}
    assert titles == {"경복궁", "남산타워"}


def test_list_all_categories_when_type_omitted(client):
    res = client.get("/api/locations")
    assert res.status_code == 200
    assert res.json()["total"] == 4  # 전체


def test_list_sort_by_likes(client):
    res = client.get("/api/locations", params={"type": "12", "sort": "likes"})
    items = res.json()["items"]
    assert items[0]["title"] == "경복궁"  # likes 10 > 5


def test_list_search_and_district(client):
    res = client.get("/api/locations", params={"type": "12", "q": "남산"})
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["title"] == "남산타워"

    res = client.get("/api/locations", params={"district": "종로구"})
    titles = {it["title"] for it in res.json()["items"]}
    assert titles == {"경복궁", "광장시장"}


def test_pagination(client):
    res = client.get("/api/locations", params={"type": "12", "size": 1, "page": 2})
    data = res.json()
    assert data["total"] == 2
    assert data["page"] == 2
    assert data["size"] == 1
    assert len(data["items"]) == 1


def test_festival_event_dates_in_response(client):
    res = client.get("/api/locations", params={"type": "15"})
    item = res.json()["items"][0]
    assert item["event_start"] == "2026-05-01"
    assert item["event_end"] == "2026-05-03"


# ---- 좋아요 / 취소 ---------------------------------------------------------

def test_like_and_unlike(client):
    # +1
    res = client.post("/api/locations/2/like")
    assert res.status_code == 200
    assert res.json() == {"id": 2, "likes": 6}

    # -1
    res = client.post("/api/locations/2/unlike")
    assert res.json()["likes"] == 5


def test_unlike_floors_at_zero(client):
    res = client.post("/api/locations/4/unlike")  # likes 0
    assert res.status_code == 200
    assert res.json()["likes"] == 0


def test_like_unknown_returns_404(client):
    res = client.post("/api/locations/9999/like")
    assert res.status_code == 404


# ---- 구 목록 ---------------------------------------------------------------

def test_districts(client):
    res = client.get("/api/locations/districts", params={"type": "12"})
    assert res.status_code == 200
    assert set(res.json()["items"]) == {"종로구", "용산구"}


# ---- 통계 ------------------------------------------------------------------

def test_stats_dashboard(client):
    res = client.get("/api/stats")
    assert res.status_code == 200
    d = res.json()

    assert d["totals"]["locations"] == 4
    assert d["totals"]["posts"] == 3
    assert d["totals"]["festivals"] == 1
    assert d["totals"]["likes_sum"] == 18  # 10+5+3+0

    cat = {x["code"]: x["count"] for x in d["locations_by_category"]}
    assert cat == {"12": 2, "15": 1, "38": 1}
    # 라벨 매핑 확인
    labels = {x["code"]: x["label"] for x in d["locations_by_category"]}
    assert labels["12"] == "관광지"

    dist = {x["district"]: x["count"] for x in d["locations_by_district"]}
    assert dist["종로구"] == 2

    assert d["top_liked"][0]["title"] == "경복궁"  # 최다 추천

    posts_cat = {x["code"]: x["count"] for x in d["posts_by_category"]}
    assert posts_cat == {"12": 2, "15": 1}

    months = {x["month"]: x["count"] for x in d["festivals_by_month"]}
    assert months == {"2026-05": 1}
