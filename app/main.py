import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app import models  # noqa: F401  (create_all 이 테이블을 인식하려면 import 필요)
from app.routers import chat, comment, locations, posts, stats

# 테이블 생성 (없으면). SQLite 파일이 없으면 이 시점에 만들어진다.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="LocalHub API", version="1.1")

# CORS — 로컬(Vite) + Netlify 배포 도메인 허용. 값은 .env / Render 환경변수로 주입.
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록 (각 파일에서 엔드포인트를 추가하면 자동 반영)
app.include_router(posts.router)
app.include_router(locations.router)
app.include_router(chat.router)
app.include_router(stats.router)
app.include_router(comment.router)


@app.get("/")
def root():
    return {"message": "LocalHub API 서버입니다."}


@app.get("/api/health")
def health():
    return {"status": "ok"}
