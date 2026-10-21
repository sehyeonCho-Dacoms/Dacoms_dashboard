"""G-R 노드 테스트 (네트워크 불필요 — sample 소스·가상 HTML·순수 함수만)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pipeline import _http
from pipeline.config import Config
from pipeline.export import write_outputs
from pipeline.gr import measure, run_gr
from pipeline.keywords import FORMAT_MODIFIERS, KEYWORD_GROUPS, build_queries
from pipeline.models import STATUS_AUTO, STATUS_MANUAL, STATUS_ROBOTS, PostRef
from pipeline.sources.naver import NaverBlogSource, parse_items, to_mobile_url
from pipeline.sources.tistory import TistoryManualSource, parse_cse_items
from pipeline.structure import analyze_html, is_question, title_patterns

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample_data"


def _config(tmp_path: Path, **kw) -> Config:
    return Config(sources=kw.pop("sources", ["sample"]), out_dir=tmp_path, sample_dir=SAMPLE, **kw)


def _html(name: str) -> str:
    return (SAMPLE / "html" / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 검색어
# --------------------------------------------------------------------------- #
def test_keywords_match_hub_table():
    assert sum(len(v) for v in KEYWORD_GROUPS.values()) == 15
    assert len(build_queries()) == 15
    assert len(build_queries(with_modifiers=True)) == 15 * (1 + len(FORMAT_MODIFIERS))


# --------------------------------------------------------------------------- #
# 제목
# --------------------------------------------------------------------------- #
def test_title_patterns():
    assert title_patterns("페이닥터 연봉 총정리 (2026 연봉표)") == ["숫자", "괄호", "총정리", "연봉표"]
    assert "질문형" in title_patterns("간호사 이직 준비, 뭐부터 해야 할까?")
    assert "하는 법" in title_patterns("병원 채용 공고 쓰기, 이렇게 하는법")
    assert is_question("세전인가요")
    assert not is_question("지방 병원이 더 높은 이유")


# --------------------------------------------------------------------------- #
# 구조 측정
# --------------------------------------------------------------------------- #
def test_naver_smart_editor_structure():
    m = analyze_html(_html("naver_1.html"), "https://m.blog.naver.com/sample_doc/100000001", "페이닥터 연봉")
    assert m.container == "se-main-container"
    assert (m.headings, m.question_headings) == (3, 1)
    assert m.tables == 1          # se-table 컴포넌트 + 안쪽 <table> 이중 집계 없음
    assert m.images == 2
    assert m.lists == 1
    assert m.has_faq
    assert m.tags == 3            # 본문 밖 post_tag 영역
    assert (m.internal_links, m.external_links) == (1, 1)  # 같은 블로그 ID = 내부
    assert m.lead_has_keyword and m.lead_has_number


def test_tistory_structure_and_published_meta():
    m = analyze_html(_html("tistory_1.html"), "https://sample-blog.tistory.com/12", "의사 헤드헌팅 수수료")
    assert m.container == "tt_article_useless_p_margin"
    assert m.headings == 3 and m.question_headings == 1
    assert m.has_faq
    assert m.tags == 2
    assert (m.internal_links, m.external_links) == (2, 1)
    assert m.published == "2026-10-05"


def test_article_fallback_ignores_outside_text():
    m = analyze_html(_html("tistory_2.html"), "https://sample-blog.tistory.com/34", "병원 채용 공고 작성법")
    assert m.container == "article"
    assert m.headings == 2 and m.lists == 1
    # 사이드바 텍스트·script는 본문 글자 수에 들어가지 않음
    m_naver = analyze_html(_html("naver_1.html"), "https://m.blog.naver.com/x/1")
    assert m_naver.body_chars < 200


def test_naver_link_between_different_blog_ids_is_external():
    html = '<div class="se-main-container"><a href="https://blog.naver.com/other/1">x</a></div>'
    m = analyze_html(html, "https://m.blog.naver.com/me/2")
    assert (m.internal_links, m.external_links) == (0, 1)


# --------------------------------------------------------------------------- #
# 소스 파싱
# --------------------------------------------------------------------------- #
def test_naver_api_items_filter_and_clean():
    q = build_queries()[0]
    items = [
        {"title": "<b>페이닥터</b> 연봉 &amp; 조건", "link": "https://blog.naver.com/a/1", "postdate": "20261001"},
        {"title": "외부 블로그", "link": "https://someone.tistory.com/3", "postdate": "20261001"},
        {"title": "둘째", "link": "https://blog.naver.com/b/2", "postdate": ""},
    ]
    refs = parse_items(items, q)
    assert [r.rank for r in refs] == [1, 2]
    assert refs[0].title == "페이닥터 연봉 & 조건"
    assert refs[0].published == "2026-10-01"
    assert refs[0].group == "의사"


def test_naver_mobile_url():
    assert to_mobile_url("https://blog.naver.com/a/123") == "https://m.blog.naver.com/a/123"
    assert (
        to_mobile_url("https://blog.naver.com/PostView.naver?blogId=a&logNo=123")
        == "https://m.blog.naver.com/a/123"
    )


def test_cse_items_keep_only_tistory():
    q = build_queries()[0]
    items = [
        {"title": "A", "link": "https://x.tistory.com/1",
         "pagemap": {"metatags": [{"article:published_time": "2026-09-01T00:00:00+09:00"}]}},
        {"title": "B", "link": "https://www.example.com/2"},
    ]
    refs = parse_cse_items(items, q)
    assert len(refs) == 1 and refs[0].published == "2026-09-01" and refs[0].channel == "tistory"


def test_tistory_manual_csv(tmp_path):
    p = tmp_path / "urls.csv"
    p.write_text("group,keyword,rank,url\n의사,페이닥터 연봉,2,https://b.tistory.com/2\n"
                 "의사,페이닥터 연봉,1,https://a.tistory.com/1\n", encoding="utf-8")
    src = TistoryManualSource(_config(tmp_path, tistory_urls_csv=str(p)))
    refs = src.search(build_queries()[0])
    assert [r.url for r in refs] == ["https://a.tistory.com/1", "https://b.tistory.com/2"]


# --------------------------------------------------------------------------- #
# 수집 기준 (RULE-11)
# --------------------------------------------------------------------------- #
def _ref() -> PostRef:
    return PostRef("naver", "의사", "페이닥터 연봉", "페이닥터 연봉", 1, "제목?", "https://blog.naver.com/a/1")


def test_pages_not_opened_when_fetch_disabled(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("네트워크 호출 금지")

    monkeypatch.setattr(_http, "get_text", boom)
    src = NaverBlogSource(_config(tmp_path, fetch_pages=False))
    rec = measure(src, _ref(), src.config)
    assert rec.status == STATUS_MANUAL
    assert rec.headings is None
    assert rec.title_patterns == ["질문형"]


def test_robots_disallow_blocks_page(tmp_path, monkeypatch):
    calls = []

    def fake_get_text(url, params=None, headers=None, timeout=15):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return "User-agent: *\nDisallow: /\n"
        raise AssertionError("robots가 막은 글을 열면 안 됨")

    monkeypatch.setattr(_http, "get_text", fake_get_text)
    monkeypatch.setattr(_http, "_robots_cache", {})
    src = NaverBlogSource(_config(tmp_path, fetch_pages=True, request_delay_sec=0))
    rec = measure(src, _ref(), src.config)
    assert rec.status == STATUS_ROBOTS
    assert calls == ["https://m.blog.naver.com/robots.txt"]


def test_robots_unreadable_is_treated_as_disallowed(monkeypatch):
    def fail(*a, **k):
        raise OSError("network")

    monkeypatch.setattr(_http, "get_text", fail)
    monkeypatch.setattr(_http, "_robots_cache", {})
    assert _http.allowed_by_robots("https://x.tistory.com/1", "bot") is False


# --------------------------------------------------------------------------- #
# 전체 실행 · 산출물
# --------------------------------------------------------------------------- #
def test_end_to_end_sample_writes_outputs_without_body(tmp_path):
    config = _config(tmp_path)
    records = run_gr(config)
    assert len(records) == 4 and all(r.status == STATUS_AUTO for r in records)

    paths = write_outputs(records, tmp_path, "test")
    data = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert data["count"] == 4

    with paths["csv"].open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["채널"] and "측정 상태" in rows[0]

    summary = paths["summary"].read_text(encoding="utf-8")
    assert "| 네이버 블로그 | 의사 |" in summary

    # 본문 문장이 어떤 산출물에도 남지 않아야 함 (허브 준칙: 본문 저장 금지)
    body_sentence = "그만두기로 마음먹은 건 작년 겨울이었어요"
    for p in paths.values():
        assert body_sentence not in p.read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("key", ["naver", "tistory_cse", "tistory_manual"])
def test_sources_without_credentials_fall_back_to_sample(tmp_path, key):
    config = Config(sources=[key], out_dir=tmp_path, sample_dir=SAMPLE,
                    naver_client_id=None, naver_client_secret=None,
                    google_cse_key=None, google_cse_cx=None, tistory_urls_csv=None)
    assert config.enabled_source_keys() == ["sample"]
