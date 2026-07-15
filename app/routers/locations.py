"""지역정보 (locations) 라우터 — 담당: B(목록)·C(지도) / 백엔드

API_CONTRACT_2.md §2 참조. 엔드포인트는 이후 커밋에서 이 파일에만 추가한다.
  - GET  /api/locations              목록 (type/q/district/sort/page/size)
  - GET  /api/locations/map          지도 핀 경량 (types/limit)
  - GET  /api/locations/districts    구 목록
  - POST /api/locations/{id}/like    좋아요 +1
  ※ 2-3 단건 조회는 v1.2 스코프 제외 — 구현하지 않음.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/locations", tags=["locations"])
