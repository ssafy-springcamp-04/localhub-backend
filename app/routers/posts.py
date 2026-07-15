"""커뮤니티 (posts) 라우터 — 담당: A / 백엔드

API_CONTRACT_2.md §1 참조. 엔드포인트는 이후 커밋에서 이 파일에만 추가한다.
  - GET    /api/posts            목록
  - GET    /api/posts/{id}       상세 (views+1)
  - POST   /api/posts            작성
  - POST   /api/posts/{id}/verify  비밀번호 확인
  - PUT    /api/posts/{id}       수정
  - DELETE /api/posts/{id}       삭제
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/posts", tags=["posts"])
