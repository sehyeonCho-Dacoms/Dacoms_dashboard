"""파이프라인 전반에서 주고받는 통일 데이터 구조.

metrics-analyzer 서브에이전트가 기대하는 컬럼(test-data/dummy-metrics.csv 와
동일한 스키마)에 맞춘다: post_id,date,topic,sport_category,format,impressions,
reach,saves,shares,clicks,profile_visits,apply_clicks

중요: Instagram Graph API가 실제로 주지 못하는 값(예: 게시물 단위 프로필 유입,
지원 클릭)은 0이나 임의 추정치로 채우지 않는다 — None으로 남기고 `data_gaps`에
사유를 기록한다. metrics-analyzer는 이미 "표본 부족/미확보 데이터는
low_confidence_flags로 분리"하는 규칙을 갖고 있으므로, 여기서 지어낸 값을
넘기면 그 규칙이 무의미해진다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

# CSV로 export할 때의 컬럼 순서 (metrics-analyzer / test-data/dummy-metrics.csv 와 동일)
CSV_FIELDS = [
    "post_id", "date", "topic", "sport_category", "format",
    "impressions", "reach", "saves", "shares", "clicks",
    "profile_visits", "apply_clicks",
]


@dataclass
class CardNewsMetric:
    """카드뉴스 게시물 1건의 성과 (소스 통일 스키마)."""

    post_id: str                 # Instagram media id
    date: str = ""                # 게시일 (YYYY-MM-DD)
    permalink: str = ""

    # ── 레지스트리(사람이 기록)에서 채워지는 캠페인 메타데이터 ──
    topic: str = ""
    sport_category: str = ""
    format: str = ""             # 채용공고형 | 정보형 | 인터뷰형 ...
    registered: bool = False     # post_registry.csv에 등록되어 있었는가

    # ── Instagram Graph API가 실제로 주는 값 ──
    reach: Optional[int] = None
    saves: Optional[int] = None
    shares: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    impressions: Optional[int] = None   # 계정/미디어 타입에 따라 미지원일 수 있음

    # ── Instagram이 게시물 단위로 신뢰성 있게 주지 않는 값 ──
    # (profile_activity 지표를 시도하되, 미지원이면 None 유지)
    profile_visits: Optional[int] = None
    # 지원 클릭은 IG 자체 지표가 아님 — 링크 클릭 트래킹(UTM 등) 연동 전까지 None
    clicks: Optional[int] = None
    apply_clicks: Optional[int] = None

    # 이 건에서 확보하지 못한 값과 사유 (metrics-analyzer의 low_confidence 판단 근거)
    data_gaps: list[str] = field(default_factory=list)

    raw: dict = field(default_factory=dict, repr=False)

    def to_dict(self, *, include_raw: bool = False) -> dict:
        d = asdict(self)
        if not include_raw:
            d.pop("raw", None)
        return d

    def to_csv_row(self) -> dict:
        """metrics-analyzer가 읽는 CSV 컬럼 형태로 변환. 값이 없으면 빈 문자열."""
        row = {}
        for f in CSV_FIELDS:
            v = getattr(self, f, None)
            row[f] = "" if v is None else v
        return row
