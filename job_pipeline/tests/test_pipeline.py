"""파이프라인 핵심 로직 테스트 (네트워크 불필요 — sample 소스/순수 함수만)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.config import Config
from pipeline.export import build_payload
from pipeline.models import JobPosting
from pipeline.scoring import build_leads, score_job, score_jobs
from pipeline.sources.sample import SampleSource
from pipeline.store import merge, prev_open_counts
from pipeline.taxonomy import infer_sector, normalize_role, sports_relevance


# --------------------------------------------------------------------------- #
# taxonomy
# --------------------------------------------------------------------------- #
def test_role_normalization():
    assert normalize_role("스포츠 마케팅 매니저") == "마케팅"
    assert normalize_role("백엔드 엔지니어(Go)") == "개발"
    assert normalize_role("데이터 분석가") == "데이터"
    assert normalize_role("프로덕트 매니저(PM)") == "기획/PM"


def test_sports_relevance_scores_and_caps():
    score, reasons = sports_relevance("나이키코리아", "스포츠 마케팅 매니저")
    assert 0 < score <= 50
    assert reasons  # 근거가 있어야 함
    none_score, _ = sports_relevance("한국세무법인", "세무 회계 담당자")
    assert none_score < score


def test_sector_inference():
    assert infer_sector("FC서울", "구단 마케팅 담당") == "구단"
    assert infer_sector("대한축구협회", "유소년 운영") == "협회"


# --------------------------------------------------------------------------- #
# is_senior
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("level,title,expected", [
    ("경력 5년 이상", "마케터", True),
    ("경력 3~5년", "담당자", False),      # 상한만 5인 미들 구간은 시니어 아님
    ("경력 3~6년", "엔지니어", True),
    ("경력 2년+", "리드 개발자", True),   # 직함이 리드면 시니어
    ("신입~경력 2년", "사원", False),
])
def test_is_senior(level, title, expected):
    job = JobPosting(source="x", source_id="1", company="c", title=title, level=level)
    assert job.is_senior is expected


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #
def test_score_job_range_and_sports_boost():
    sporty = score_job(JobPosting(source="s", source_id="1", company="FC서울",
                                  title="구단 스포츠 마케팅 매니저", role="마케팅", sector="구단"))
    dull = score_job(JobPosting(source="s", source_id="2", company="일반상사",
                                title="총무 담당", role="기타"))
    assert 0 <= sporty.drafton_fit <= 100
    assert sporty.drafton_fit > dull.drafton_fit
    assert sporty.fit_reasons


def test_build_leads_tiers_and_sort():
    jobs = [
        JobPosting(source="s", source_id=str(i), company="스마트스코어",
                   title="백엔드 엔지니어", level="경력 5년 이상", sector="스포츠테크")
        for i in range(3)
    ] + [
        JobPosting(source="s", source_id="z", company="소형브랜드",
                   title="사원", level="신입", sector="브랜드")
    ]
    leads = build_leads(jobs)
    # 점수 내림차순 정렬
    assert [l.lead_score for l in leads] == sorted(
        [l.lead_score for l in leads], reverse=True
    )
    top = leads[0]
    assert top.company == "스마트스코어"
    assert top.open_roles == 3
    assert top.est_fee > 0


def test_weekly_growth_uses_previous_counts():
    prev = [JobPosting(source="s", source_id="a", company="번핏", title="개발")]
    now = [
        JobPosting(source="s", source_id="a", company="번핏", title="개발"),
        JobPosting(source="s", source_id="b", company="번핏", title="마케터"),
        JobPosting(source="s", source_id="c", company="번핏", title="PM"),
    ]
    leads = build_leads(now, prev_open=prev_open_counts(prev))
    burnfit = next(l for l in leads if l.company == "번핏")
    assert burnfit.weekly_growth == 2  # 1 → 3


# --------------------------------------------------------------------------- #
# store 병합 — 워크플로 상태 유지
# --------------------------------------------------------------------------- #
def test_merge_preserves_workflow_status():
    old = JobPosting(source="s", source_id="1", company="c", title="t", status="업로드완료")
    new = JobPosting(source="s", source_id="1", company="c", title="t (수정)", status="신규")
    merged = merge([old], [new])
    assert len(merged) == 1
    assert merged[0].title == "t (수정)"       # 내용은 갱신
    assert merged[0].status == "업로드완료"      # 사람이 정한 상태는 유지


# --------------------------------------------------------------------------- #
# sample 소스 → 통일 스키마 (오프라인)
# --------------------------------------------------------------------------- #
def test_sample_source_collects_and_normalizes(tmp_path: Path):
    raw = [{"id": "1", "company": "골프존", "title": "프로덕트 매니저(골프 SaaS)",
            "level": "경력 5년 이상", "sector": "스포츠테크", "postedAt": "2026-07-01"}]
    p = tmp_path / "raw.json"
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    cfg = Config(sources=["sample"], sample_path=p)
    jobs = SampleSource(cfg).collect()
    assert len(jobs) == 1
    j = jobs[0]
    assert j.company == "골프존"
    assert j.role == "기획/PM"       # taxonomy 보강
    assert j.sector == "스포츠테크"


# --------------------------------------------------------------------------- #
# export payload 형태 (대시보드 계약)
# --------------------------------------------------------------------------- #
def test_export_payload_shape():
    jobs = score_jobs([
        JobPosting(source="sample", source_id="1", company="FC서울",
                   title="스포츠 마케팅 매니저", role="마케팅", level="경력 5년 이상",
                   sector="구단", company_size="중소기업", posted_at="2026-07-10"),
    ])
    leads = build_leads(jobs)
    payload = build_payload(jobs, leads)
    for key in ("schema", "generatedAt", "kpis", "jobs", "leads", "actions", "trends"):
        assert key in payload
    assert payload["kpis"]["collected"] == 1
    assert {"supply", "demand"} <= set(payload["actions"])
    assert "weekly" in payload["trends"]
    # 대시보드가 참조하는 job 필드 존재
    assert {"platform", "company", "fit", "status"} <= set(payload["jobs"][0])


def test_enabled_sources_skip_without_credentials():
    cfg = Config(sources=["saramin", "worknet", "wanted", "sample"])
    # 자격증명 없음 → sample 만 남아야 함
    assert cfg.enabled_source_keys() == ["sample"]
