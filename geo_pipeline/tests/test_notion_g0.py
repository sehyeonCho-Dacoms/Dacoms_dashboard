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


def test_row_has_no_summary_and_maps_flags():
    r = notion_g0.row(_a(1, flags=["논쟁", "기타"]), "2026-10-26", "db")
    p = r["properties"]
    assert p["제목"]["title"][0]["text"]["content"] == "전공의 복귀 1"
    assert p["표시"]["multi_select"] == [{"name": "논쟁"}]
    assert p["발행 시각"]["date"]["start"].startswith("2026-10-26T09:00")
    assert "요약" not in str(r)


def test_push_only_new_passed(monkeypatch):
    calls = []

    def fake(method, url, payload=None, headers=None, timeout=0):
        calls.append((method, url))
        if url.endswith("/query"):
            return {"results": [{"properties": {"기사 ID": {"rich_text": [{"plain_text": "N-20261026-0001"}]}}}]}
        return {}

    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(notion_g0._http, "request_json", fake)
    msg = notion_g0.push([_a(1), _a(2), _a(3, screen="탈락")], datetime(2026, 10, 26, tzinfo=KST), pause=0)
    assert [u for m, u in calls if u.endswith("/pages")] == ["https://api.notion.com/v1/pages"]   # 2번만 새로
    assert "통과 2건 중 새 기사 1건" in msg
