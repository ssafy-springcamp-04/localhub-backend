"""댓글(comments) API 테스트 — 작성/목록/수정/삭제 + 비밀번호 검증.

기존 테스트와 get_db 오버라이드가 충돌하지 않도록 픽스처에서 설정·복원.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Post

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        db.add(Post(id=1, category="12", title="글", content="본문", password="1234"))
        db.commit()
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


def _create(client, content="첫 댓글", password="1234"):
    return client.post(
        "/api/posts/1/comments", json={"content": content, "password": password}
    )


def test_create_and_list(client):
    res = _create(client, "안녕하세요")
    assert res.status_code == 201
    body = res.json()
    assert body["content"] == "안녕하세요"
    assert body["post_id"] == 1
    assert "password" not in body
    assert body["updated_at"] is None

    res = client.get("/api/posts/1/comments")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["content"] == "안녕하세요"
    assert "password" not in data["items"][0]


def test_create_on_missing_post_404(client):
    res = client.post(
        "/api/posts/999/comments", json={"content": "x", "password": "1234"}
    )
    assert res.status_code == 404


def test_verify_password(client):
    cid = _create(client).json()["id"]
    assert client.post(f"/api/comments/{cid}/verify", json={"password": "1234"}).status_code == 200
    r = client.post(f"/api/comments/{cid}/verify", json={"password": "0000"})
    assert r.status_code == 403


def test_update(client):
    cid = _create(client, "원본").json()["id"]
    # 틀린 비번
    r = client.put(f"/api/comments/{cid}", json={"password": "0000", "content": "수정"})
    assert r.status_code == 403
    # 맞는 비번
    r = client.put(f"/api/comments/{cid}", json={"password": "1234", "content": "수정됨"})
    assert r.status_code == 200
    assert r.json()["content"] == "수정됨"
    assert r.json()["updated_at"] is not None


def test_delete(client):
    cid = _create(client).json()["id"]
    # 틀린 비번
    assert client.request("DELETE", f"/api/comments/{cid}", json={"password": "0000"}).status_code == 403
    # 맞는 비번
    r = client.request("DELETE", f"/api/comments/{cid}", json={"password": "1234"})
    assert r.status_code == 204
    # 목록 비어있음
    assert client.get("/api/posts/1/comments").json()["total"] == 0


def test_delete_post_cascades_comments(client):
    _create(client, "댓글1")
    _create(client, "댓글2")
    assert client.get("/api/posts/1/comments").json()["total"] == 2
    # 게시글 삭제 → 댓글도 함께 삭제
    r = client.request("DELETE", "/api/posts/1", json={"password": "1234"})
    assert r.status_code == 204
    # 게시글이 없으니 댓글 목록 조회는 404
    assert client.get("/api/posts/1/comments").status_code == 404
