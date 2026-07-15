"""챗봇 (chat) 라우터 — 담당: B / 백엔드

API_CONTRACT_2.md §3 참조. 엔드포인트는 이후 커밋에서 이 파일에만 추가한다.
  - POST /api/chat   질의 프록시 (OpenAI). 오류/타임아웃 시 503.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/chat", tags=["chat"])
