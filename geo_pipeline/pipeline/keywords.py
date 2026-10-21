"""G-R 수집 검색어 사전 (노션: 블로그 GEO 체인 — 모범 글 구조 분석).

1차 검색어 15개 × 채널별 상위 5개 → 채널당 약 75개.
검색어를 바꾸려면 코드가 아니라 이 표를 고친다(허브 표와 같은 순서 유지).
"""

from __future__ import annotations

from dataclasses import dataclass

# 묶음 → 1차 검색어. 허브 표의 '묶음' 이름 그대로.
KEYWORD_GROUPS: dict[str, list[str]] = {
    "의사": [
        "페이닥터 연봉",
        "봉직의 이직",
        "지방 병원 의사 연봉",
        "의사 근로계약서",
        "공보의 전역 후 진로",
        "개원 vs 봉직",
    ],
    "반의사": [
        "간호사 이직 준비",
        "병원 원무과 업무",
        "병원 행정직 취업",
        "병원 채용 공고 작성법",
    ],
    "의료 업계 뉴스": [
        "의대 정원",
        "전공의 복귀",
        "필수의료 정책",
    ],
    "비교·브랜드": [
        "의사 구인구직 사이트",
        "의사 헤드헌팅 수수료",
    ],
}

# 2차 수집용 형식 수식어 (검색어 뒤에 붙인다). 제목 패턴 판별에도 쓴다.
FORMAT_MODIFIERS: list[str] = ["총정리", "비교", "후기", "하는 법", "체크리스트", "연봉표", "Q&A"]


@dataclass(frozen=True)
class Query:
    group: str        # 묶음
    keyword: str      # 1차 검색어
    query: str        # 실제 검색 문자열 (2차면 수식어 포함)
    modifier: str = ""


def build_queries(with_modifiers: bool = False) -> list[Query]:
    """1차 검색어 목록. with_modifiers=True면 검색어 × 수식어 2차 목록을 덧붙인다."""
    out: list[Query] = []
    for group, kws in KEYWORD_GROUPS.items():
        for kw in kws:
            out.append(Query(group, kw, kw))
    if with_modifiers:
        for group, kws in KEYWORD_GROUPS.items():
            for kw in kws:
                for mod in FORMAT_MODIFIERS:
                    out.append(Query(group, kw, f"{kw} {mod}", mod))
    return out
