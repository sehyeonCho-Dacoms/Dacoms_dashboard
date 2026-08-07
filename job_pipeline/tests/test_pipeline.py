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


def test_ksoc_needs_no_credential():
    # 대한체육회는 공개 게시판이라 키 없이도 활성
    assert Config(sources=["ksoc"]).enabled_source_keys() == ["ksoc"]


# --------------------------------------------------------------------------- #
# 대한체육회(eGov 게시판) 크롤러 파서 — 표준 마크업 픽스처 (네트워크 불필요)
# --------------------------------------------------------------------------- #
KSOC_FIXTURE = """
<table class="board_list"><thead><tr><th>번호</th><th>제목</th><th>등록일</th></tr></thead>
<tbody>
  <tr>
    <td>공지</td>
    <td class="subject"><a href="view.do?nttId=10521&amp;bbsId=BMSR00024&amp;menuNo=200027&amp;pageIndex=1">2026년 대한체육회 일반직 직원 채용 공고</a></td>
    <td>2026-07-20</td><td>1523</td>
  </tr>
  <tr>
    <td>102</td>
    <td class="subject"><a href="#none" onclick="fn_view('10498'); return false;">스포츠 마케팅 담당자 채용</a></td>
    <td>2026.07.15</td><td>842</td>
  </tr>
  <tr>
    <td>101</td>
    <td class="subject"><a href="./view.do?dataSid=10477&amp;menuNo=200027">체육회관 시설 운영 담당자 모집</a></td>
    <td>2026/07/10</td><td>301</td>
  </tr>
</tbody></table>
<div class="pagination"><a href="list.do?pageIndex=2">다음</a></div>
"""


def _ksoc_source():
    from pipeline.sources.ksoc import KsocSource
    return KsocSource(Config(sources=["ksoc"]))


def test_ksoc_parses_egov_board_rows():
    rows = _ksoc_source()._parse_list(KSOC_FIXTURE)
    # 헤더/페이지네이션 제외, 실제 공고 3건
    assert len(rows) == 3
    titles = [r["title"] for r in rows]
    assert "2026년 대한체육회 일반직 직원 채용 공고" in titles
    assert "스포츠 마케팅 담당자 채용" in titles
    # 날짜 정규화 (다양한 구분자 → YYYY-MM-DD)
    dates = {r["date"] for r in rows}
    assert {"2026-07-20", "2026-07-15", "2026-07-10"} == dates


def test_ksoc_builds_detail_urls_and_ids():
    rows = {r["title"]: r for r in _ksoc_source()._parse_list(KSOC_FIXTURE)}
    # href view.do → 절대 URL로 결합
    r1 = rows["2026년 대한체육회 일반직 직원 채용 공고"]
    assert r1["id"] == "10521"
    assert r1["url"].startswith("https://sports.or.kr/sports/bbs/BMSR00024/view.do")
    assert "nttId=10521" in r1["url"]
    # onclick 함수 인자에서 ID 추출 → URL 구성
    r2 = rows["스포츠 마케팅 담당자 채용"]
    assert r2["id"] == "10498"
    assert "bbsId=BMSR00024" in r2["url"] and "menuNo=200027" in r2["url"]
    # dataSid 파라미터도 인식
    assert rows["체육회관 시설 운영 담당자 모집"]["id"] == "10477"


def test_ksoc_normalize_sets_association_sector():
    src = _ksoc_source()
    rows = src._parse_list(KSOC_FIXTURE)
    jobs = [src.normalize(r) for r in rows]
    assert all(j is not None for j in jobs)
    for j in jobs:
        assert j.source == "ksoc"
        assert j.company == "대한체육회"
        assert j.sector == "협회"
        assert j.company_size == "공공/협회"
    # 직무 정규화(taxonomy)까지 적용
    by_title = {j.title: j for j in jobs}
    assert by_title["스포츠 마케팅 담당자 채용"].role == "마케팅"
    assert by_title["체육회관 시설 운영 담당자 모집"].role == "운영"


def test_ksoc_scores_prioritize_sports_roles():
    src = _ksoc_source()
    from pipeline.scoring import score_job
    jobs = {j.title: score_job(j) for j in (src.normalize(r) for r in src._parse_list(KSOC_FIXTURE))}
    # 스포츠 마케팅 = 핵심 직무 + 협회 직접공고 → 업로드 강력 권장
    assert jobs["스포츠 마케팅 담당자 채용"].drafton_fit >= 70
    # 일반 행정직도 협회 직접공고라 최소한 검토 대상(중간 점수)
    assert jobs["2026년 대한체육회 일반직 직원 채용 공고"].drafton_fit >= 50


# --------------------------------------------------------------------------- #
# 구글 검색(Custom Search API) 소스 — 순수 파싱/정규화만 (네트워크 불필요)
# --------------------------------------------------------------------------- #
from pipeline.sources.gsearch import (
    GoogleSearchSource,
    _clean_title,
    _guess_company,
    _looks_like_posting,
)


def test_gsearch_needs_credentials_to_enable():
    # API 키/cx 없으면 자동 skip → sample 로 폴백
    assert Config(sources=["gsearch"]).enabled_source_keys() == ["sample"]
    cfg = Config(sources=["gsearch"], google_cse_api_key="k", google_cse_id="cx")
    assert cfg.enabled_source_keys() == ["gsearch"]


@pytest.mark.parametrize("link,expected", [
    ("https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=12345", True),
    ("https://www.jobkorea.co.kr/Recruit/GI_Read/98765?Gno=1", True),
    ("https://www.saramin.co.kr/zf_user/help/notice", False),
    ("https://www.jobkorea.co.kr/", False),
])
def test_looks_like_posting_filters_noise(link, expected):
    assert _looks_like_posting(link) is expected


def test_guess_company_extracts_when_pattern_clear():
    # "회사명 - 공고제목" 형태: 직무 신호가 있는 쪽이 아닌, 짧은 쪽을 회사명으로
    company, confident = _guess_company("나이키코리아 - 스포츠 마케팅 매니저 채용")
    assert confident is True
    assert company == "나이키코리아"


def test_guess_company_gives_up_when_ambiguous():
    # 구분자가 없거나 양쪽 다 애매하면 확신 없음(False) 처리
    company, confident = _guess_company("스포츠 산업 채용 트렌드 총정리")
    assert confident is False
    assert company is None


def test_clean_title_strips_site_suffix():
    assert _clean_title("스포츠 마케팅 매니저 채용 - 사람인") == "스포츠 마케팅 매니저 채용"
    assert _clean_title("골프존 채용공고 | 잡코리아") == "골프존 채용공고"


def _gsearch_source():
    return GoogleSearchSource(Config(sources=["gsearch"], google_cse_api_key="k", google_cse_id="cx"))


def test_gsearch_normalize_confident_company_is_verified():
    src = _gsearch_source()
    raw = {
        "title": "나이키코리아 - 스포츠 마케팅 매니저 채용",
        "link": "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=1",
        "snippet": "나이키코리아에서 스포츠 마케팅 매니저를 채용합니다.",
        "_site": "saramin.co.kr",
    }
    job = src.normalize(raw)
    assert job is not None
    assert job.verified_company is True
    assert job.company == "나이키코리아"
    assert job.source == "gsearch_saramin"


def test_gsearch_normalize_ambiguous_company_is_unverified():
    src = _gsearch_source()
    raw = {
        "title": "2026 스포츠 업계 채용 동향 리포트",
        "link": "https://www.jobkorea.co.kr/Recruit/GI_Read/5555?Gno=1",
        "snippet": "스포츠 업계 채용이 활발합니다.",
        "_site": "jobkorea.co.kr",
    }
    job = src.normalize(raw)
    assert job is not None
    assert job.verified_company is False
    assert job.company == "확인필요(원문 참조)"
    assert job.source == "gsearch_jobkorea"


def test_gsearch_normalize_rejects_non_posting_links():
    src = _gsearch_source()
    raw = {"title": "사람인 공지사항", "link": "https://www.saramin.co.kr/zf_user/help/notice",
           "snippet": "", "_site": "saramin.co.kr"}
    assert src.normalize(raw) is None


def test_gsearch_fetch_respects_daily_query_cap(monkeypatch):
    import pipeline.sources.gsearch as gsearch_mod

    calls = {"n": 0}

    def fake_get_json(url, params=None, headers=None, timeout=15):
        calls["n"] += 1
        return {"items": []}

    monkeypatch.setattr(gsearch_mod._http, "get_json", fake_get_json)
    cfg = Config(
        sources=["gsearch"], google_cse_api_key="k", google_cse_id="cx",
        keywords=["스포츠", "골프", "구단"], google_cse_sites=["saramin.co.kr", "jobkorea.co.kr"],
        google_cse_daily_cap=3,
    )
    GoogleSearchSource(cfg).fetch()
    # 2사이트 x 3키워드 = 6개 쿼리가 가능하지만 캡(3)에서 멈춰야 함
    assert calls["n"] == 3


# --------------------------------------------------------------------------- #
# 회사명 미확인(verified_company=False) 공고의 다운스트림 처리
# --------------------------------------------------------------------------- #
def test_unverified_company_excluded_from_lead_building():
    jobs = [
        JobPosting(source="gsearch_jobkorea", source_id="1", company="확인필요(원문 참조)",
                   title="스포츠 마케터 채용", verified_company=False, sector="브랜드"),
        JobPosting(source="ksoc", source_id="2", company="대한체육회",
                   title="운영 담당자", verified_company=True, sector="협회"),
    ]
    leads = build_leads(jobs)
    companies = {l.company for l in leads}
    assert "확인필요(원문 참조)" not in companies
    assert "대한체육회" in companies


def test_unverified_company_downgrades_supply_action_cta():
    # 구단(고독점성) 섹터 + 핵심 직무로 고의로 고득점(>=88)을 만들어, 확신이었다면
    # P0가 나올 상황에서도 verified_company=False면 P0로 올라가지 않는지 검증.
    job = JobPosting(source="gsearch_saramin", source_id="1", company="확인필요(원문 참조)",
                      title="스포츠 마케팅 구단 담당자 채용", role="마케팅", sector="구단",
                      verified_company=False)
    score_job(job)
    assert job.drafton_fit >= 88
    payload = build_payload([job], [])
    assert payload["actions"]["supply"], "적합도 임계값을 넘어 supply 액션이 생성돼야 함"
    action = payload["actions"]["supply"][0]
    assert action["cta"] == "원문 확인 후 업로드"
    assert action["pr"] == "P1"  # 미확인 공고는 고득점이어도 P0(지금 업로드)로 올라가지 않음


def test_score_job_flags_unverified_company_reason():
    job = JobPosting(source="gsearch_saramin", source_id="1", company="확인필요(원문 참조)",
                      title="스포츠 마케팅 담당자", verified_company=False)
    score_job(job)
    assert any("회사명 미확인" in r for r in job.fit_reasons)
