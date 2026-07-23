"""대시보드 공급용 JSON 생성.

dashboard.html 이 fetch('./data/dashboard.json') 로 읽는 최종 산출물을 만든다.
KPI·인게스트 목록·리드 보드·오늘의 액션·트렌드 집계를 모두 서버(파이썬)에서
계산해 넘겨, 프런트는 렌더만 담당하게 한다(관심사 분리).
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import DASHBOARD_SCHEMA_VERSION, CompanyLead, JobPosting

UPLOAD_FIT_THRESHOLD = 70


def build_payload(jobs: list[JobPosting], leads: list[CompanyLead]) -> dict:
    fit_ok = [j for j in jobs if j.drafton_fit >= UPLOAD_FIT_THRESHOLD]
    hot = [l for l in leads if l.tier == "Hot"]
    pipeline_value = sum(l.est_fee for l in hot)  # 만원 단위

    kpis = {
        "collected": len(jobs),
        "uploadReady": len(fit_ok),
        "uploadReadyPct": round(len(fit_ok) / len(jobs) * 100) if jobs else 0,
        "hotLeads": len(hot),
        "pipelineValue": pipeline_value,
        "pipelineValueLabel": _won_label(pipeline_value),
    }

    return {
        "schema": DASHBOARD_SCHEMA_VERSION,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "kpis": kpis,
        "jobs": [_job_view(j) for j in sorted(jobs, key=lambda x: x.drafton_fit, reverse=True)],
        "leads": [_lead_view(l) for l in leads],
        "actions": _build_actions(jobs, leads),
        "trends": _build_trends(jobs, leads),
    }


def write_dashboard_json(path: Path, jobs: list[JobPosting], leads: list[CompanyLead]) -> dict:
    payload = build_payload(jobs, leads)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


# --------------------------------------------------------------------------- #
def _job_view(j: JobPosting) -> dict:
    return {
        "platform": _platform_label(j.source),
        "company": j.company,
        "title": j.title,
        "role": j.role,
        "level": j.level,
        "size": j.company_size or "중소기업",
        "sector": j.sector,
        "fit": j.drafton_fit,
        "reasons": j.fit_reasons,
        "status": j.status,
        "url": j.url,
    }


def _lead_view(l: CompanyLead) -> dict:
    return {
        "company": l.company,
        "sector": l.sector,
        "open": l.open_roles,
        "growth": f"+{l.weekly_growth}" if l.weekly_growth else "±0",
        "senior": l.senior_roles,
        "tier": l.tier,
        "score": l.lead_score,
        "fee": l.est_fee,
        "stage": l.stage,
        "signal": " · ".join(l.signals),
    }


def _build_actions(jobs: list[JobPosting], leads: list[CompanyLead]) -> dict:
    """'오늘의 액션' — 데이터에서 실행 항목을 자동 도출."""
    supply = []
    for j in sorted(jobs, key=lambda x: x.drafton_fit, reverse=True):
        if j.status == "업로드완료" or j.drafton_fit < UPLOAD_FIT_THRESHOLD:
            continue
        supply.append({
            "pr": "P0" if j.drafton_fit >= 88 else "P1",
            "title": f"{j.company} · {j.title} 업로드",
            "company": f"{_platform_label(j.source)} · 적합도 {j.drafton_fit}",
            "why": " / ".join(j.fit_reasons) or "스포츠 연관 공고 — 인벤토리 확대",
            "cta": "지금 업로드",
        })
        if len(supply) >= 3:
            break

    demand = []
    for l in leads:
        if l.tier == "Nurture":
            continue
        demand.append({
            "pr": "P0" if l.tier == "Hot" else "P1",
            "title": f"{l.company} 헤드헌팅 {'계약 제안' if l.tier == 'Hot' else '접촉'}",
            "company": f"예상 수수료 ₩{l.est_fee:,}만",
            "why": " · ".join(l.signals),
            "cta": "제안서 발송" if l.tier == "Hot" else "콜드 아웃리치",
        })
        if len(demand) >= 3:
            break

    return {"supply": supply, "demand": demand}


def _build_trends(jobs: list[JobPosting], leads: list[CompanyLead]) -> dict:
    role = _count(j.role for j in jobs)
    size = _count((j.company_size or "중소기업") for j in jobs)
    platform = _count(_platform_label(j.source) for j in jobs)
    sector = defaultdict(int)
    for l in leads:
        sector[l.sector] += l.open_roles

    # 경력 구간
    level = {"신입~주니어": 0, "미들(3~5년)": 0, "시니어(5년+)": 0}
    for j in jobs:
        if j.is_senior:
            level["시니어(5년+)"] += 1
        elif any(k in (j.level or "") for k in ("신입", "1년", "2년", "무관")):
            level["신입~주니어"] += 1
        else:
            level["미들(3~5년)"] += 1

    return {
        "role": role,
        "size": size,
        "platform": platform,
        "sector": dict(sorted(sector.items(), key=lambda x: x[1], reverse=True)),
        "level": level,
        "weekly": _weekly_series(jobs),
    }


def _weekly_series(jobs: list[JobPosting]) -> dict:
    """posted_at 기준 최근 8주 유입/적합 시계열. 날짜가 없으면 빈 시리즈."""
    dated = [j for j in jobs if j.posted_at]
    if not dated:
        return {"labels": [], "total": [], "uploadReady": []}
    today = date.today()
    labels, total, ready = [], [], []
    for w in range(7, -1, -1):
        start = today - timedelta(days=(w + 1) * 7)
        end = today - timedelta(days=w * 7)
        labels.append("이번주" if w == 0 else f"{w}주전")
        bucket = [j for j in dated if start < _as_date(j.posted_at) <= end]
        total.append(len(bucket))
        ready.append(sum(1 for j in bucket if j.drafton_fit >= UPLOAD_FIT_THRESHOLD))
    return {"labels": labels, "total": total, "uploadReady": ready}


# --------------------------------------------------------------------------- #
_PLATFORM = {
    "saramin": "사람인", "worknet": "워크넷", "wanted": "원티드",
    "jumpit": "점핏", "jobkorea": "잡코리아", "sample": "샘플",
}


def _platform_label(source: str) -> str:
    return _PLATFORM.get(source, source)


def _won_label(man: int) -> str:
    """만원 단위 정수를 사람이 읽는 라벨로. 예: 24000 -> '₩2.4억'."""
    if man >= 10000:
        return f"₩{man / 10000:.1f}억"
    return f"₩{man:,}만"


def _count(values) -> dict:
    c: dict[str, int] = defaultdict(int)
    for v in values:
        c[v] += 1
    return dict(sorted(c.items(), key=lambda x: x[1], reverse=True))


def _as_date(s: str) -> date:
    try:
        return datetime.fromisoformat(s[:10]).date()
    except Exception:
        return date.min
