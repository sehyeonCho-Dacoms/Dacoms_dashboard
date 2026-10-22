"""G0 이슈 트래커 테스트 (네트워크 불필요 — 가상 기사·순수 함수만)."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

from pipeline import _http
from pipeline.config import Config
from pipeline.export import pick_calibration, write_g0_outputs
from pipeline.g0 import run_g0
from pipeline.models import SCREEN_DROP, SCREEN_PASS, Article
from pipeline.screen import screen, title_key
from pipeline.sources.news import KST, NaverNewsSource, parse_date, parse_feed, parse_naver_news

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample_data"
NOW = datetime(2026, 10, 21, 10, 0, tzinfo=KST)


def _config(tmp_path: Path, **kw) -> Config:
    return Config(g0_sources=kw.pop("g0_sources", ["sample"]), out_dir=tmp_path, sample_dir=SAMPLE,
                  g0_rss_feeds=kw.pop("g0_rss_feeds", []), g0_queries=kw.pop("g0_queries", []), **kw)


def _a(title: str, desc: str = "", hours: int = 1) -> Article:
    return Article(title=title, url="https://x.example/1", description=desc, published=NOW - timedelta(hours=hours))


# --------------------------------------------------------------------------- #
# 거름망
# --------------------------------------------------------------------------- #
def test_screen_passes_workforce_news_and_flags_controversy():
    a = screen(_a("필수의료 수가 인상안에 의사단체 반발"), NOW)
    assert a.screen == SCREEN_PASS and a.flags == ["논쟁"]


def test_screen_reasons():
    assert screen(_a("대학병원 항암 신약 임상시험 결과"), NOW).screen_reasons[0].startswith("①")
    assert screen(_a("기업 이사회 의사결정 구조 개편"), NOW).screen_reasons == ["① 주제 밖(제목에 의료 단어 없음)"]
    assert screen(_a("병원 홍보 행사 개최"), NOW).screen_reasons == ["① 주제 밖(제목에 인력·채용 단어 없음)"]
    assert screen(_a("전문의가 알려주는 감기 증상과 예방법"), NOW).screen_reasons == ["② 의료 조언형(증상·예방법)"]
    assert screen(_a("병원 운영 혐의로 의사 기소"), NOW).screen_reasons[0].startswith("③")
    assert screen(_a("전공의 복귀 찌라시 확산"), NOW).screen_reasons[0].startswith("④")
    old = screen(_a("전공의 복귀 현황", hours=24 * 8), NOW)
    assert old.screen == SCREEN_DROP and "⑤ 7일 지남" in old.screen_reasons


def test_first_run_false_positives_are_dropped():
    # 10/21 첫 실행에서 통과됐던 유형: 요약의 '의사를 밝혔다', 제목의 '정원'·'의정'
    a = screen(_a("대통령 \"처벌 원치 않아\"…수사 종결 수순", "처벌을 원하지 않는다는 의사를 밝혔다"), NOW)
    assert a.screen == SCREEN_DROP and a.screen_reasons[0].startswith("① 주제 밖(제목에 의료 단어 없음)")
    b = screen(_a("시의회, 하천 정원 조성 예산 의정 활동 보고"), NOW)
    assert b.screen == SCREEN_DROP
    c = screen(_a("일본·중국 노선 여객 급증…항공 여객 역대 최다"), NOW)
    assert c.screen == SCREEN_DROP


def test_calibration_false_passes_are_dropped_by_title_rule():
    # 10/22 채점 보정에서 사람·Claude가 ① 주제 밖으로 본 기사: 요약의 '인력'·'근무'로 통과했었다
    kt = screen(_a("KT, 전국 병원 관계자 60여 명에 의료 AI 모델 소개", "간호 인력 근무 일정 관리"), NOW)
    expo = screen(_a("보건의료 통합행사 '코메드 2026' 개최", "의료 인력 채용 박람회 부스"), NOW)
    assert kt.screen == SCREEN_DROP and expo.screen == SCREEN_DROP
    assert screen(_a('"상주 의사 0명"…장애인선수촌 의료 공백 질타'), NOW).screen == SCREEN_PASS
    assert screen(_a("대학병원 신약 임상시험 결과"), NOW).screen_reasons == [
        "① 주제 밖(제목에 인력·채용 단어 없음: 신약·임상시험)"
    ]


def test_legal_flag():
    a = screen(_a("봉직의 근로계약서 분쟁 늘어…퇴직금 판결 잇따라"), NOW)
    assert a.screen == SCREEN_PASS and "법률" in a.flags
    both = screen(_a("전공의 파업 관련 의료법 개정안 반발"), NOW)
    assert both.flags == ["논쟁", "법률"]


def test_outputs_do_not_include_article_summaries(tmp_path):
    articles = run_g0(_config(tmp_path), NOW)
    assert any(a.description for a in articles)               # 메모리에는 있다 (거름망 판단용)
    paths = write_g0_outputs(articles, tmp_path, "d")
    for p in paths.values():
        text = p.read_text(encoding="utf-8-sig")
        assert "가상 기사." not in text                         # 샘플 요약 문구가 파일에 없어야 함
    assert "요약" not in paths["csv"].read_text(encoding="utf-8-sig").splitlines()[0]


def test_cap_keeps_passed_articles_first(tmp_path):
    stats: dict = {}
    articles = run_g0(_config(tmp_path, g0_max=4), NOW, stats)
    assert len(articles) == 4 and all(a.screen == SCREEN_PASS for a in articles)
    assert (stats["deduped"], stats["passed"]) == (11, 5)
    summary = write_g0_outputs(articles, tmp_path, "d", stats)["summary"].read_text(encoding="utf-8")
    assert "검토 11건" in summary and "거름망 통과 5건 → 통과 기사 먼저 4건 기록" in summary


def test_offtopic_title_kept_when_title_is_about_workforce():
    a = screen(_a("신약 개발 바이오 기업, 의사 채용 확대"), NOW)
    assert a.screen == SCREEN_PASS


def test_title_key_ignores_bracket_prefix_and_punctuation():
    assert title_key("[단독] 전공의 복귀율, 50% 넘어") == title_key("전공의 복귀율 50% 넘어")


# --------------------------------------------------------------------------- #
# 소스 파싱
# --------------------------------------------------------------------------- #
def test_parse_naver_news_items():
    items = [{
        "title": "<b>전공의</b> 복귀 &quot;속도&quot;",
        "originallink": "https://press.example/1",
        "link": "https://n.news.naver.com/mnews/article/001/0001",
        "description": "요약 <b>전공의</b>",
        "pubDate": "Tue, 21 Oct 2026 09:30:00 +0900",
    }]
    a = parse_naver_news(items, "전공의")[0]
    assert a.title == '전공의 복귀 "속도"'
    assert a.url == "https://press.example/1"
    assert a.naver_url.startswith("https://n.news.naver.com")
    assert a.published == datetime(2026, 10, 21, 9, 30, tzinfo=KST)


def test_naver_news_endpoint_and_auth(tmp_path):
    src = NaverNewsSource(_config(tmp_path, naver_client_id="i", naver_client_secret="s"))
    assert src.endpoint() == "https://naverapihub.apigw.ntruss.com/search/v1/news"
    legacy = NaverNewsSource(_config(tmp_path, naver_api_mode="legacy"))
    assert legacy.endpoint() == "https://openapi.naver.com/v1/search/news.json"


def test_parse_rss_and_atom():
    rss = """<rss><channel><item><title>전공의 &amp; 수련</title><link>https://p.example/1</link>
      <pubDate>Tue, 21 Oct 2026 08:00:00 +0900</pubDate><description>요약</description></item></channel></rss>"""
    atom = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>의대 정원</title>
      <link href="https://p.example/2"/><updated>2026-10-21T00:00:00Z</updated></entry></feed>"""
    r = parse_feed(rss)[0]
    assert (r.title, r.url, r.published.hour) == ("전공의 & 수련", "https://p.example/1", 8)
    a = parse_feed(atom)[0]
    assert a.url == "https://p.example/2" and a.published == datetime(2026, 10, 21, 9, 0, tzinfo=KST)
    assert parse_feed("<not xml") == []


def test_parse_date_handles_missing_and_iso():
    assert parse_date("") is None
    assert parse_date("2026-10-21T01:00:00+00:00").hour == 10


# --------------------------------------------------------------------------- #
# 전체 실행
# --------------------------------------------------------------------------- #
def test_run_g0_sample_window_dedupe_and_cap(tmp_path):
    articles = run_g0(_config(tmp_path), NOW)
    titles = [a.title for a in articles]
    assert len(articles) == 11                                  # 40시간 전 1건 제외, 재전송 1건 제외
    assert not any("의대 정원 조정" in t for t in titles)
    assert sum("봉직의 연봉" in t for t in titles) == 1
    passed = [a for a in articles if a.screen == SCREEN_PASS]
    assert articles[: len(passed)] == passed                    # 통과 기사가 앞에
    assert [a.published for a in passed] == sorted((a.published for a in passed), reverse=True)
    assert all(a.id == f"N-{a.published:%Y%m%d}-{a.id[-4:]}" and a.press for a in articles)

    capped = run_g0(_config(tmp_path, g0_max=3), NOW)
    assert len(capped) == 3


def test_g0_outputs_and_calibration(tmp_path):
    articles = run_g0(_config(tmp_path), NOW)
    picks = pick_calibration(articles)
    assert len(picks) == 5 and all(a.screen == SCREEN_PASS for a in picks)

    paths = write_g0_outputs(articles, tmp_path, "2026-10-21")
    with paths["csv"].open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 11 and rows[0]["기사 ID"].startswith("N-")
    summary = paths["summary"].read_text(encoding="utf-8")
    assert "## 채점 보정용 5건" in summary and "① 주제 밖" in summary


def test_naver_news_fetch_survives_one_failed_query(tmp_path, monkeypatch):
    calls = []

    def fake(url, params=None, headers=None, timeout=15):
        calls.append(params["query"])
        if params["query"] == "bad":
            raise OSError("boom")
        return {"items": [{"title": "전공의", "originallink": f"https://p.example/{params['query']}",
                           "pubDate": "Tue, 21 Oct 2026 09:00:00 +0900"}]}

    monkeypatch.setattr(_http, "get_json", fake)
    src = NaverNewsSource(_config(tmp_path, g0_queries=["bad", "ok"], request_delay_sec=0,
                                  naver_client_id="i", naver_client_secret="s"))
    got = src.fetch()
    assert calls == ["bad", "ok"] and len(got) == 1


def test_g0_sources_without_credentials_fall_back_to_sample(tmp_path):
    c = _config(tmp_path, g0_sources=["naver_news", "rss"], naver_client_id=None, naver_client_secret=None)
    assert c.enabled_g0_source_keys() == ["sample"]
