"""G-R 노드가 주고받는 데이터 구조.

허브 준칙: 본문 전문은 저장하지 않고 '구조 지표와 링크'만 남긴다.
그래서 `StructureRecord`에는 본문 텍스트 필드가 없다. 측정용 텍스트는
분석 함수 안에서만 쓰고 버린다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

# 구조 지표 측정 상태
STATUS_AUTO = "자동 측정"
STATUS_MANUAL = "사람 기록"        # GR_FETCH_PAGES=false
STATUS_ROBOTS = "robots 차단"      # robots.txt가 막음 → 사람이 열어 기록
STATUS_ERROR = "열기 실패"


@dataclass
class PostRef:
    """검색 결과 한 건 (목록 단계)."""

    channel: str          # naver | tistory
    group: str            # 묶음 (의사/반의사/…)
    keyword: str          # 1차 검색어
    query: str            # 실제 검색 문자열
    rank: int             # 검색 순위 (1부터)
    title: str
    url: str
    published: str = ""   # YYYY-MM-DD
    source: str = ""      # 소스 키


@dataclass
class StructureRecord:
    """글 한 건의 구성 기록. 허브 '글마다 기록할 항목'과 1:1."""

    channel: str
    group: str
    keyword: str
    query: str
    rank: int
    title: str
    url: str
    published: str = ""
    source: str = ""
    status: str = STATUS_MANUAL

    # 제목
    title_len: int = 0
    title_patterns: list[str] = field(default_factory=list)   # 질문형·숫자·괄호·수식어

    # 본문 구조 (자동 측정. 못 재면 None → 사람 기록)
    lead_chars: Optional[int] = None          # 첫 3문장 글자 수
    lead_has_keyword: Optional[bool] = None   # 첫 3문장에 검색어 핵심 단어가 있나 (답 여부는 사람 확인)
    lead_has_number: Optional[bool] = None
    headings: Optional[int] = None            # 소제목 수
    question_headings: Optional[int] = None   # 그중 질문형
    body_chars: Optional[int] = None          # 본문 글자 수 (공백 제외)
    images: Optional[int] = None
    tables: Optional[int] = None
    lists: Optional[int] = None
    has_faq: Optional[bool] = None
    external_links: Optional[int] = None      # 출처 링크 후보
    internal_links: Optional[int] = None
    tags: Optional[int] = None

    # 자동으로 못 재는 항목 (사람이 열어 기록)
    image_kinds: str = ""        # 직접 찍음·캡처·표 이미지
    author_profile: str = ""     # 작성자 소개 노출
    likes: Optional[int] = None  # 공감
    comments: Optional[int] = None
    note: str = ""

    @classmethod
    def from_ref(cls, ref: PostRef) -> "StructureRecord":
        return cls(**asdict(ref))

    def to_dict(self) -> dict:
        return asdict(self)
