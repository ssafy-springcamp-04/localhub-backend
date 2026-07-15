import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# SQLite 경로는 환경변수로 (기본값: 프로젝트 루트 localhub.db)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./localhub.db")

# SQLite 는 기본 단일 스레드라서 FastAPI 다중 스레드용으로 해제
connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI 의존성: 요청마다 세션 생성 후 종료."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
