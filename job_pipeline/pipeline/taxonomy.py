"""도메인 사전(taxonomy): 스포츠 연관 키워드, 직무 분류, 섹터/규모 추론.

normalize와 scoring이 공유한다. 실서비스에서는 이 사전을 계속 늘려가며 정확도를
개선하는 것이 핵심 — 데이터가 아니라 '판단 기준'을 코드로 관리한다.
"""

from __future__ import annotations

# 스포츠 산업 연관 키워드 (가중치). 회사명/제목/설명/산업에서 매칭.
SPORTS_KEYWORDS: dict[str, int] = {
    # 강한 신호
    "스포츠": 10, "sport": 10, "athletic": 8, "구단": 10, "프로축구": 10,
    "프로야구": 10, "농구": 8, "배구": 8, "골프": 9, "피트니스": 8, "헬스": 6,
    "테니스": 8, "러닝": 6, "클라이밍": 7, "e스포츠": 9, "esports": 9, "게임단": 8,
    # 브랜드/리테일
    "스포츠웨어": 9, "애슬레저": 8, "아웃도어": 6, "스니커즈": 5,
    # 조직/기관
    "협회": 6, "연맹": 7, "리그": 8, "체육": 7, "선수": 7, "코치": 6, "트레이너": 6,
    "스폰서십": 8, "스포츠마케팅": 12, "스포츠테크": 12, "스포츠데이터": 11,
    # 영문 브랜드/일반
    "nike": 8, "adidas": 8, "fitness": 8, "league": 6, "club": 4, "stadium": 6,
}

# 알려진 스포츠 기업(정확 매칭 시 강한 부스트) — 실서비스에서 확장
KNOWN_SPORTS_COMPANIES = {
    "나이키", "아디다스", "언더아머", "뉴발란스", "데카트론", "휠라", "아식스",
    "데상트", "룰루레몬", "골프존", "스마트스코어", "번핏", "스포츠몬스터",
    "스포티비", "spotv", "갤럭시아sm", "스포츠투아이", "fc서울", "울산hd",
    "대한축구협회", "kbl", "kbo", "한국프로골프협회",
}

# 직무 정규화: (매칭 키워드들) -> 표준 카테고리
ROLE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("스포츠마케팅", "브랜드마케", "퍼포먼스마케", "마케터", "마케팅", "그로스", "crm", "홍보", "브랜딩"), "마케팅"),
    (("md", "머천다이", "바이어", "상품기획"), "MD"),
    (("데이터", "analyst", "분석", "ml", "머신러닝", "ai"), "데이터"),
    (("백엔드", "프론트", "개발", "engineer", "developer", "sw", "서버", "ios", "android", "devops"), "개발"),
    (("pm", "프로덕트", "기획", "product manager"), "기획/PM"),
    (("운영", "operation", "매장", "스토어", "cs", "고객"), "운영"),
    (("콘텐츠", "pd", "미디어", "영상", "에디터", "크리에이터", "방송"), "미디어"),
    (("bd", "사업개발", "제휴", "세일즈", "영업", "스폰서십"), "사업개발"),
    (("코치", "트레이너", "강사", "감독", "선수"), "코치/트레이너"),
]

# 섹터 추론: 키워드 -> 섹터
SECTOR_RULES: list[tuple[tuple[str, ...], str]] = [
    (("협회", "연맹", "체육회"), "협회"),
    (("fc", "구단", "게임단", "프로", "야구단", "축구단", "농구단"), "구단"),
    (("spotv", "스포티비", "방송", "미디어", "콘텐츠", "ott"), "미디어"),
    (("에이전시", "매니지먼트", "갤럭시아", "스폰서십"), "에이전시"),
    (("테크", "소프트", "saas", "플랫폼", "데이터", "앱", "스코어"), "스포츠테크"),
    (("나이키", "아디다스", "언더아머", "데카트론", "휠라", "브랜드", "웨어", "리테일"), "브랜드"),
]

# 기업 규모 힌트 (회사명/설명 기준의 러프 추론; 소스가 값을 주면 그 값 우선)
SIZE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("코리아", "그룹", "holdings"), "대기업"),
    (("협회", "연맹", "공단", "진흥원"), "공공/협회"),
    (("스타트업", "labs", "스코어", "핏"), "스타트업"),
]


def normalize_role(*texts: str) -> str:
    blob = " ".join(t.lower() for t in texts if t)
    for keys, label in ROLE_RULES:
        if any(k in blob for k in keys):
            return label
    return "기타"


def infer_sector(*texts: str) -> str:
    blob = " ".join(t.lower() for t in texts if t)
    for keys, label in SECTOR_RULES:
        if any(k in blob for k in keys):
            return label
    return "기타"


def infer_size(existing: str, *texts: str) -> str:
    if existing:
        return existing
    blob = " ".join(t.lower() for t in texts if t)
    for keys, label in SIZE_HINTS:
        if any(k in blob for k in keys):
            return label
    return "중소기업"


def sports_relevance(*texts: str) -> tuple[int, list[str]]:
    """0~50 스포츠 연관 점수와 매칭 근거를 반환."""
    blob = " ".join(t.lower() for t in texts if t)
    score = 0
    hits: list[str] = []
    for company in KNOWN_SPORTS_COMPANIES:
        if company in blob:
            score += 20
            hits.append(f"스포츠 기업({company})")
            break
    for kw, w in SPORTS_KEYWORDS.items():
        if kw in blob:
            score += w
            hits.append(kw)
    score = min(score, 50)
    # 근거는 상위 3개만 노출
    return score, hits[:3]
