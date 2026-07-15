from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

SQLITE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_posts_api_flow():
    # 1) 글 작성
    response = client.post(
        "/api/posts",
        json={
            "category": "39",
            "title": "테스트 제목",
            "content": "테스트 내용",
            "password": "1234",
        },
    )
    assert response.status_code == 201
    created = response.json()
    assert created["id"] == 1
    assert created["category"] == "39"
    assert created["title"] == "테스트 제목"
    assert created["content"] == "테스트 내용"
    assert "password" not in created
    assert created["views"] == 0
    assert created["updated_at"] is None

    # 2) 목록 조회
    response = client.get("/api/posts")
    assert response.status_code == 200
    list_data = response.json()
    assert list_data["page"] == 1
    assert list_data["size"] == 10
    assert list_data["total"] == 1
    assert isinstance(list_data["items"], list)
    assert list_data["items"][0]["id"] == 1
    assert "content" not in list_data["items"][0]
    assert "password" not in list_data["items"][0]

    # 3) 상세 조회 및 조회수 증가
    response = client.get("/api/posts/1")
    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == 1
    assert detail["views"] == 1
    assert detail["content"] == "테스트 내용"

    # 4) 비밀번호 확인
    response = client.post("/api/posts/1/verify", json={"password": "1234"})
    assert response.status_code == 200
    assert response.json() == {"verified": True}

    # 5) 수정
    response = client.put(
        "/api/posts/1",
        json={
            "password": "1234",
            "category": "39",
            "title": "수정 제목",
            "content": "수정 내용",
        },
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "수정 제목"
    assert updated["content"] == "수정 내용"
    assert updated["updated_at"] is not None

    # 6) 잘못된 비밀번호 삭제 실패
    response = client.request(
        "DELETE",
        "/api/posts/1",
        json={"password": "0000"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "비밀번호가 일치하지 않습니다."

    # 7) 올바른 비밀번호로 삭제
    response = client.request(
        "DELETE",
        "/api/posts/1",
        json={"password": "1234"},
    )
    assert response.status_code == 204
    assert response.content == b""

    # 확인: 삭제 후 404
    response = client.get("/api/posts/1")
    assert response.status_code == 404
