"""챗봇 (chat) 라우터 — 담당: B / 백엔드

API_CONTRACT_2.md §3. POST /api/chat 질의 프록시.
스키마는 이 파일에 로컬 정의 (담당별 파일 분리 원칙).
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import chatbot

router = APIRouter(prefix="/api/chat", tags=["chat"])

# OpenAI 오류/타임아웃 시 반환 문구 (계약서 §3-1 고정)
ERROR_503_DETAIL = "챗봇 응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요."


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    history: list[ChatMessage] = Field(default_factory=list)


class Source(BaseModel):
    type: Literal["location", "post"]
    id: int
    title: str


class ChatResponse(BaseModel):
    reply: str
    sources: list[Source] = Field(default_factory=list)


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    # 이중 방어: 서버에서도 history 10턴 초과분 절단 (비용 상한 조항)
    history = req.history[-chatbot.MAX_HISTORY_MESSAGES:]
    try:
        reply, sources = chatbot.answer(db, req.message, history)
    except chatbot.ChatServiceError:
        raise HTTPException(status_code=503, detail=ERROR_503_DETAIL)
    return ChatResponse(reply=reply, sources=sources)
