"""파이프라인 전반에서 주고받는 통일(normalized) 데이터 구조.

각 채용 플랫폼(사람인·워크넷·원티드 …)의 응답은 소스별로 스키마가 제각각이므로,
normalize 단계에서 아래 `JobPosting` 하나로 통일한다. 대시보드/스코어링/스토어는
모두 이 통일 스키마만 알면 된다.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Optional


# 워크플로 상태 (공고 인게스트)
STATUS_NEW = "신규"
STATUS_REVIEW = "검토중"
STATUS_UPLOADED = "업로드완료"
JOB_STATUSES = {STATUS_NEW, STATUS_REVIEW, STATUS_UPLOADED}

# CRM 단계 (헤드헌팅 리드)
STAGE_NEW = "신규"
STAGE_CONTACT = "접촉"
STAGE_MEETING = "미팅"
STAGE_PROPOSAL = "제안"
LEAD_STAGES = {STAGE_NEW, STAGE_CONTACT, STAGE_MEETING, STAGE_PROPOSAL}


def _slug(*parts: str) -> str:
    raw = "|".join(p.strip().lower() for p in parts if p)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class JobPosting:
    """한 건의 채용 공고 (소스 통일 스키마)."""

    source: str                 # 소스 키: saramin | worknet | wanted | sample
    source_id: str              # 소스 내부 고유 ID
    company: str
    title: str
    url: str = ""
    role: str = "기타"          # 정규화된 직무 카테고리 (마케팅/개발/데이터 …)
    level: str = "경력무관"     # 경력 구간 표기
    location: str = ""
    employment_type: str = ""   # 정규직/계약직 …
    company_size: str = ""      # 대기업/중견기업/중소기업/스타트업/공공·협회
    sector: str = ""            # 브랜드/스포츠테크/구단/미디어/에이전시/협회
    salary: str = ""
    posted_at: str = ""         # ISO 날짜 문자열 (YYYY-MM-DD)
    deadline: str = ""
    description: str = ""

    # 스코어링 결과 (scoring 단계에서 채움)
    drafton_fit: int = 0        # 0~100 드래프트온 업로드 적합도
    fit_reasons: list[str] = field(default_factory=list)

    # 워크플로 (스토어 병합 시 유지)
    status: str = STATUS_NEW

    # 원천 응답 보관 (디버깅용, export 시 제외)
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def key(self) -> str:
        """중복 판정 키. 소스+소스ID가 있으면 그것을, 없으면 회사+제목 해시."""
        if self.source and self.source_id:
            return f"{self.source}:{self.source_id}"
        return f"{self.source or 'unknown'}:{_slug(self.company, self.title)}"

    @property
    def is_senior(self) -> bool:
        """시니어(5년+) 포지션 여부 — 헤드헌팅 수수료 단가 산정에 사용.

        '경력 3~5년'처럼 상한만 5인 미들 구간은 시니어로 보지 않는다.
        '5년 이상' 또는 6년+, 혹은 리드/팀장급 직함일 때만 시니어로 판정.
        """
        text = self.level or ""
        nums = [int(n) for n in re.findall(r"(\d+)", text)]
        if nums and max(nums) >= 6:
            return True
        if "이상" in text and nums and max(nums) >= 5:
            return True
        blob = f"{self.level} {self.title}".lower()
        strong = ("시니어", "리드", "lead", "팀장", "책임", "총괄", "수석", "head", "senior", "principal")
        return any(k in blob for k in strong)

    def to_dict(self, *, include_raw: bool = False) -> dict:
        d = asdict(self)
        if not include_raw:
            d.pop("raw", None)
        return d


@dataclass
class CompanyLead:
    """공고들을 회사 단위로 집계한 헤드헌팅 리드 (CRM 카드)."""

    company: str
    sector: str = ""
    open_roles: int = 0
    senior_roles: int = 0
    weekly_growth: int = 0      # 직전 수집 대비 신규 공고 수 (히스토리 있으면)
    lead_score: int = 0         # 0~100
    tier: str = "Nurture"       # Hot | Warm | Nurture
    est_fee: int = 0            # 예상 헤드헌팅 수수료 (단위: 만원)
    signals: list[str] = field(default_factory=list)
    stage: str = STAGE_NEW      # CRM 단계 (스토어 병합 시 유지)
    sample_titles: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# 대시보드가 기대하는 export 스키마 버전
DASHBOARD_SCHEMA_VERSION = 1
