"""G0 → 노션 행 테스트 (네트워크 불필요)."""

from __future__ import annotations

from datetime import datetime

from pipeline import notion_g0
from pipeline.models import Article
from pipeline.sources.news import KST


def _a(i, screen="통과", flags=()):
    return Article(title=f"전공의 복귀 {i}", url=f"https://news.example/{i}", id=f"N-20261026-000{i}",
                   press="news.example", query="전공의", screen=screen, flags=list(flags),
                   published=datetime(2026, 10, 26, 9, 0, tzinfo=KST), description="요약은 넣지 않음")


def test_row_goes_to_chain_db_as_first_stage():
    r = notion_g0.row(_a(1, flags=["논쟁"]), "2026-10-26", "db")
    p = r["properties"]
    assert p["글 번호"]["title"][0]["text"]["content"] == "N-20261026-0001"
    assert p["제목"]["rich_text"][0]["text"]["content"] == "전공의 복귀 1"
    assert p["원천 기사"]["url"] == "https://news.example/1" and p["상태"]["select"]["name"] == "질문선택"
    assert "표시 논쟁" in p["작업 기록"]["rich_text"][0]["text"]["content"]
    assert "요약" not in str(r)


def test_push_only_new_passed(monkeypatch):
    calls = []

    def fake(method, url, payload=None, headers=None, timeout=0):
        calls.append((method, url))
        if url.endswith("/query"):
            return {"results": [{"properties": {"글 번호": {"title": [{"plain_text": "N-20261026-0001"}]}}}]}
        return {}

    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(notion_g0._http, "request_json", fake)
    msg = notion_g0.push([_a(1), _a(2), _a(3, screen="탈락")], datetime(2026, 10, 26, tzinfo=KST), pause=0)
    assert [u for m, u in calls if u.endswith("/pages")] == ["https://api.notion.com/v1/pages"]   # 2번만 새로
    assert "통과 2건 중 새 기사 1건" in msg


def test_candidate_rows_news_and_evergreen():
    from pipeline import g2
    now = datetime(2026, 10, 27, 10, 0, tzinfo=KST)
    s = g2.score(Article(title="울산시, 지역필수의사 구인난에 자격완화 검토", url="https://n.example/1", id="N-1",
                         press="n.example", published=now), now)
    rows = notion_g0.candidate_rows([s], [g2.BY_ID[20]], "2026-10-27", "db")
    p = rows[0]["properties"]
    assert p["종류"]["select"]["name"] == "뉴스" and p["총점"]["number"] == s.total and p["순위"]["number"] == 1
    assert p["원천 기사"]["url"] == "https://n.example/1" and p["매칭 질문"]["rich_text"][0]["text"]["content"].startswith("GQ-")
    q = rows[1]["properties"]
    assert q["종류"]["select"]["name"] == "상록 슬롯" and q["순위"]["number"] == 2
    assert q["후보"]["title"][0]["text"]["content"].startswith("GQ-20")


def test_push_candidates_skips_same_day(monkeypatch):
    calls = []

    def fake(method, url, payload=None, headers=None, timeout=0):
        calls.append(url)
        return {"results": [{"id": "x"}]} if url.endswith("/query") else {}

    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(notion_g0._http, "request_json", fake)
    msg = notion_g0.push_candidates([], [], datetime(2026, 10, 27, tzinfo=KST))
    assert "이미 있어 건너뜀" in msg and not any(u.endswith("/pages") for u in calls)
