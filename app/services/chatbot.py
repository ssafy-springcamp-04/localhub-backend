"""챗봇 서비스 — API_CONTRACT_2.md §3-1

2일 일정용 최소 구조 (Function calling·임베딩 등 고급 기법 미사용):
  1) 사용자 질문에서 질의 유형 판별 + 키워드 추출
  2) locations / posts 를 LIKE 로 DB 검색해 컨텍스트 확보
  3) 검색 결과를 컨텍스트로 붙여 OpenAI 에 답변 생성 요청

대응 질의 유형 4종: 관광지 추천(12) · 축제 일정(15) · 모범음식점(39) · 게시글 검색(posts)
OpenAI 오류/타임아웃/키 미설정 → ChatServiceError 발생 → 라우터에서 503 변환.
"""
import os
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Location, Post

# ── 설정 (API 키·모델·타임아웃은 전부 환경변수. 코드/저장소에 키 하드코딩 금지) ──
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "20"))
# temperature 는 환경변수로 줄 때만 전달. 미설정 시 모델 기본값 사용.
# (gpt-5 계열 등 일부 모델은 temperature 커스텀 값을 거부하므로 기본은 미전달)
OPENAI_TEMPERATURE = os.getenv("OPENAI_TEMPERATURE")

# 서버측 이중 방어: history 는 최대 10턴(=메시지)까지만 모델에 전달 (비용 상한 조항)
MAX_HISTORY_MESSAGES = 10
MAX_CONTEXT_ITEMS = 6   # OpenAI 에 붙일 검색 결과 상한
MAX_SOURCES = 5         # 응답 sources 상한

# 질의 유형 → locations.content_type_id
INTENT_CONTENT_TYPE = {
    "tourist": "12",     # 관광지 추천
    "festival": "15",    # 축제 일정
    "restaurant": "39",  # 모범음식점
}

CATEGORY_LABELS = {
    "12": "관광지", "14": "문화시설", "15": "축제공연행사", "25": "여행코스",
    "28": "레포츠", "32": "숙박", "38": "쇼핑", "39": "음식점",
}

# 유형 판별 키워드 (우선순위: 축제 > 음식점 > 게시글 > 관광지 > 일반)
FESTIVAL_KEYWORDS = ("축제", "행사", "공연", "페스티벌", "축제일정")
RESTAURANT_KEYWORDS = ("맛집", "음식", "식당", "먹거리", "모범음식", "레스토랑", "식사")
POST_KEYWORDS = ("게시글", "게시판", "커뮤니티", "후기", "글 ", "질문글")
TOURIST_KEYWORDS = ("관광", "명소", "가볼", "여행지", "구경", "볼거리", "나들이")

# 검색 키워드에서 제외할 흔한 조사/불용어
STOPWORDS = {
    "추천", "알려줘", "알려", "해줘", "해주세요", "어디", "무엇", "뭐", "있어", "있나요",
    "근처", "주변", "이번", "주말", "오늘", "내일", "요즘", "그리고", "인기", "좋은",
    "서울", "서울시", "서울특별시", "정보", "관련", "대해", "관해",
}

SYSTEM_PROMPT = (
    "당신은 서울 지역정보(관광지·문화시설·축제·맛집)와 커뮤니티 게시글을 안내하는 챗봇입니다. "
    "아래 [검색된 컨텍스트]에 있는 실제 데이터를 근거로 한국어로 친절하고 간결하게 답하세요. "
    "목록은 번호와 개행(\\n)으로 구분해 읽기 쉽게 제시하세요. "
    "컨텍스트에 없는 구체적 사실(주소·전화·일정 등)은 지어내지 말고, 정보가 없으면 솔직히 안내하세요. "
    "데이터 출처는 한국관광공사(TourAPI)입니다."
)


class ChatServiceError(Exception):
    """OpenAI 호출 실패·타임아웃·키 미설정 등. 라우터에서 503 으로 변환."""


def detect_intent(message: str) -> str:
    if any(k in message for k in FESTIVAL_KEYWORDS):
        return "festival"
    if any(k in message for k in RESTAURANT_KEYWORDS):
        return "restaurant"
    if any(k in message for k in POST_KEYWORDS):
        return "post"
    if any(k in message for k in TOURIST_KEYWORDS):
        return "tourist"
    return "general"


def extract_keywords(message: str) -> list[str]:
    tokens = re.findall(r"[가-힣A-Za-z0-9]+", message)
    seen: list[str] = []
    for t in tokens:
        if len(t) >= 2 and t not in STOPWORDS and t not in seen:
            seen.append(t)
    return seen


def search_locations(
    db: Session, keywords: list[str], content_type_id: str | None = None
) -> list[Location]:
    stmt = select(Location)
    if content_type_id:
        stmt = stmt.where(Location.content_type_id == content_type_id)
    if keywords:
        conds = []
        for k in keywords:
            like = f"%{k}%"
            conds.extend(
                [
                    Location.title.like(like),
                    Location.addr1.like(like),
                    Location.district.like(like),
                ]
            )
        stmt = stmt.where(or_(*conds))
    stmt = stmt.order_by(Location.likes.desc()).limit(MAX_CONTEXT_ITEMS)
    return list(db.execute(stmt).scalars().all())


def search_posts(db: Session, keywords: list[str]) -> list[Post]:
    stmt = select(Post)
    if keywords:
        conds = []
        for k in keywords:
            like = f"%{k}%"
            conds.extend([Post.title.like(like), Post.content.like(like)])
        stmt = stmt.where(or_(*conds))
    stmt = stmt.order_by(Post.created_at.desc()).limit(MAX_CONTEXT_ITEMS)
    return list(db.execute(stmt).scalars().all())


def gather_context(
    db: Session, message: str
) -> tuple[str, list[Location], list[Post]]:
    intent = detect_intent(message)
    keywords = extract_keywords(message)

    locations: list[Location] = []
    posts: list[Post] = []

    if intent == "post":
        posts = search_posts(db, keywords)
    elif intent in INTENT_CONTENT_TYPE:
        locations = search_locations(db, keywords, INTENT_CONTENT_TYPE[intent])
        if not locations:  # 유형 필터로 못 찾으면 전체에서 재검색
            locations = search_locations(db, keywords)
    else:  # general: 장소 + 게시글 모두 탐색
        locations = search_locations(db, keywords)
        posts = search_posts(db, keywords)

    return intent, locations, posts


def format_context(locations: list[Location], posts: list[Post]) -> str:
    lines: list[str] = []
    if locations:
        lines.append("[장소 정보]")
        for loc in locations:
            parts = [f"- (id={loc.id}) {loc.title}"]
            if loc.addr1:
                parts.append(f"주소: {loc.addr1}")
            if loc.tel:
                parts.append(f"전화: {loc.tel}")
            label = CATEGORY_LABELS.get(loc.content_type_id)
            if label:
                parts.append(f"분류: {label}")
            lines.append(" / ".join(parts))
    if posts:
        lines.append("[게시글]")
        for p in posts:
            snippet = (p.content or "").strip().replace("\n", " ")[:80]
            lines.append(f"- (id={p.id}) {p.title} : {snippet}")
    if not lines:
        return "(검색된 관련 데이터가 없습니다. 일반적인 안내만 제공하고 구체적 사실은 추측하지 마세요.)"
    return "\n".join(lines)


def build_sources(locations: list[Location], posts: list[Post]) -> list[dict]:
    out: list[dict] = []
    for loc in locations:
        out.append({"type": "location", "id": loc.id, "title": loc.title})
    for p in posts:
        out.append({"type": "post", "id": p.id, "title": p.title})
    return out[:MAX_SOURCES]


def _build_messages(message: str, history: list, context_text: str) -> list[dict]:
    system = f"{SYSTEM_PROMPT}\n\n[검색된 컨텍스트]\n{context_text}"
    messages = [{"role": "system", "content": system}]
    # 서버측 이중 절단 (프론트가 이미 자르지만 비용 상한 재방어)
    for h in history[-MAX_HISTORY_MESSAGES:]:
        role = getattr(h, "role", None) or h["role"]
        content = getattr(h, "content", None) or h["content"]
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    return messages


def _generate_reply(messages: list[dict]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ChatServiceError("OPENAI_API_KEY 미설정")
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=OPENAI_TIMEOUT)
        kwargs = {"model": OPENAI_MODEL, "messages": messages}
        if OPENAI_TEMPERATURE is not None:
            kwargs["temperature"] = float(OPENAI_TEMPERATURE)
        resp = client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()
    except ChatServiceError:
        raise
    except Exception as exc:  # OpenAI API 오류·타임아웃 등 전부 503 대상
        raise ChatServiceError(str(exc)) from exc


def answer(db: Session, message: str, history: list) -> tuple[str, list[dict]]:
    """(reply, sources) 반환. 실패 시 ChatServiceError."""
    _intent, locations, posts = gather_context(db, message)
    context_text = format_context(locations, posts)
    messages = _build_messages(message, history, context_text)
    reply = _generate_reply(messages)
    sources = build_sources(locations, posts)
    return reply, sources
