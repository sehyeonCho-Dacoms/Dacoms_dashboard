"""스코어링 엔진.

1) drafton_fit : 이 공고를 드래프트온에 올릴 가치 (0~100)
     = 스포츠 연관성(0~50) + 직무 매칭(0~30) + 독점성(0~20)
2) lead_score  : 이 회사를 헤드헌팅으로 접근할 가치 (0~100)
     = 채용 속도(0~45) + 시니어 비중(0~35) + 접근성(0~20)
3) est_fee     : 예상 헤드헌팅 수수료(만원) — 시니어 수 × 섹터 단가

임계값·가중치는 상단 상수로 모아 두어 운영하며 튜닝한다.
"""

from __future__ import annotations

from collections import defaultdict

from .models import CompanyLead, JobPosting
from .taxonomy import sports_relevance

# 우리가 드래프트온에 원하는 핵심 직무 (매칭 시 가점)
TARGET_ROLES = {"마케팅", "MD", "데이터", "개발", "기획/PM", "운영", "미디어", "사업개발"}

# 대형 채용 플랫폼(이미 노출 많음) → 독점성 낮음 / 구단·협회 직접공고 → 독점성 높음
LOW_EXCLUSIVITY_SECTORS = {"브랜드"}
HIGH_EXCLUSIVITY_SECTORS = {"구단", "협회", "에이전시"}

# 이 섹터로 분류됐다는 것 자체가 스포츠 산업 기업이라는 신호 → 연관성 하한 보장
SPORTS_SECTORS = {"협회", "구단", "스포츠테크", "에이전시", "미디어", "브랜드"}
SECTOR_RELEVANCE_FLOOR = 40

# 리드 티어 임계값 (단일 크롤 규모 기준으로 보정 — 주간 momentum이 붙으면 상향)
TIER_HOT = 62
TIER_WARM = 48

# 섹터별 시니어 1인 예상 수수료(만원) — 연봉×수수료율 러프 추정
SECTOR_FEE = {
    "스포츠테크": 1300, "브랜드": 900, "미디어": 800, "에이전시": 950,
    "구단": 700, "협회": 650, "기타": 700,
}


def score_job(job: JobPosting) -> JobPosting:
    """공고 하나의 drafton_fit 계산 (in-place로 채워 반환)."""
    rel, reasons = sports_relevance(job.company, job.title, job.description, job.sector)

    # 스포츠 섹터로 분류된 공고는 최소한의 연관성을 보장(일반 직무여도 스포츠 산업 잡)
    if job.sector in SPORTS_SECTORS and rel < SECTOR_RELEVANCE_FLOOR:
        rel = SECTOR_RELEVANCE_FLOOR
        reasons.append(f"{job.sector} 섹터 확정")

    role_pts = 30 if job.role in TARGET_ROLES else 5
    if job.role in TARGET_ROLES:
        reasons.append(f"핵심 직무({job.role})")

    if job.sector in HIGH_EXCLUSIVITY_SECTORS:
        excl = 20
        reasons.append("독점 인벤토리 가능(직접공고)")
    elif job.sector in LOW_EXCLUSIVITY_SECTORS:
        excl = 6
    else:
        excl = 12

    job.drafton_fit = max(0, min(100, rel + role_pts + excl))
    job.fit_reasons = reasons[:3]
    return job


def score_jobs(jobs: list[JobPosting]) -> list[JobPosting]:
    return [score_job(j) for j in jobs]


def _tier(score: int) -> str:
    if score >= TIER_HOT:
        return "Hot"
    if score >= TIER_WARM:
        return "Warm"
    return "Nurture"


def build_leads(
    jobs: list[JobPosting],
    prev_open: dict[str, int] | None = None,
) -> list[CompanyLead]:
    """공고들을 회사 단위로 집계해 헤드헌팅 리드 목록을 만든다.

    prev_open: {회사명: 직전 수집 공개 공고 수} — 주간 증가폭(weekly_growth) 계산용.
    """
    prev_open = prev_open or {}
    by_company: dict[str, list[JobPosting]] = defaultdict(list)
    for j in jobs:
        by_company[j.company].append(j)

    leads: list[CompanyLead] = []
    for company, group in by_company.items():
        open_roles = len(group)
        senior = sum(1 for j in group if j.is_senior)
        sector = _dominant(j.sector for j in group)
        growth = open_roles - prev_open.get(company, open_roles)

        # 채용 속도 (0~40): 공개 공고 수 + 주간 증가폭(momentum)
        velocity = min(open_roles * 9, 27) + max(0, min(growth * 7, 13))
        # 시니어 비중 (0~35): 고연봉 포지션일수록 수수료 단가↑
        senior_ratio = senior / open_roles if open_roles else 0
        seniority = round(senior_ratio * 22) + min(senior * 5, 13)
        # 접근성 (0~25): 대형 브랜드는 이미 HH 많음 → 낮게, 구단/협회/테크는 높게
        if sector in HIGH_EXCLUSIVITY_SECTORS or sector == "스포츠테크":
            reach = 25
        elif sector == "브랜드":
            reach = 8
        else:
            reach = 14

        score = max(0, min(100, velocity + seniority + reach))
        est_fee = senior * SECTOR_FEE.get(sector, 700) + (open_roles - senior) * 300

        signals: list[str] = []
        if growth >= 2:
            signals.append(f"{growth}건↑ 채용 확대 중(스케일업 신호)")
        if open_roles >= 3:
            signals.append(f"{open_roles}개 직무 동시 채용 — 스케일업 정황")
        if senior_ratio >= 0.4:
            signals.append("시니어 비중 높음 → 수수료 단가 상승")
        if sector in HIGH_EXCLUSIVITY_SECTORS:
            signals.append("HH 저경쟁 · 선점 가치 큼")
        if not signals:
            signals.append("관계 구축 단계 · 지속 모니터링")

        leads.append(
            CompanyLead(
                company=company,
                sector=sector,
                open_roles=open_roles,
                senior_roles=senior,
                weekly_growth=max(0, growth),
                lead_score=score,
                tier=_tier(score),
                est_fee=est_fee,
                signals=signals[:2],
                sample_titles=[j.title for j in group[:3]],
            )
        )

    leads.sort(key=lambda l: l.lead_score, reverse=True)
    return leads


def _dominant(values) -> str:
    counts: dict[str, int] = defaultdict(int)
    for v in values:
        if v:
            counts[v] += 1
    return max(counts, key=counts.get) if counts else "기타"
