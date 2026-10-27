"""G3 선택 → 체인 DB 행 테스트 (네트워크 불필요)."""

from __future__ import annotations

from datetime import date, datetime

from pipeline import g3
from pipeline.sources.news import KST


def _page(pid="abcd1234-0000", kind="뉴스", channel="둘 다", question="GQ-4 병원에서 의사를 빨리 채용하는 방법은?",
          target="병원", total=70, url="https://news.example/1", marks=("논쟁",)):
    t = lambda s: {"type": "rich_text", "rich_text": [{"plain_text": s}]}
    return {"id": pid, "properties": {
        "후보": {"type": "title", "title": [{"plain_text": "울산시 지역필수의사 구인난"}]},
        "날짜": {"type": "date", "date": {"start": "2026-10-27"}},
        "종류": {"type": "select", "select": {"name": kind}},
        "총점": {"type": "number", "number": total},
        "점수 내역": t("A25 B20 C8 D10 E5 F2"),
        "타깃": {"type": "select", "select": {"name": target}},
        "채널": {"type": "select", "select": {"name": channel}},
        "매칭 질문": t(question),
        "원천 기사": {"type": "url", "url": url},
        "표시": {"type": "multi_select", "multi_select": [{"name": m} for m in marks]},
        "한 줄 이유": t("병원 구인난 · 지역의사"),
        "메모": t(""),
    }}


def _props(row):
    p = row["properties"]
    get = lambda k: "".join(x["text"]["content"] for x in p[k].get("rich_text", p[k].get("title", [])))
    return p, get


def test_news_both_channels_makes_pair_with_required_fields():
    c = g3.from_page(_page())
    rows = g3.rows_for(c, 8, date(2026, 10, 28), "db")
    assert len(rows) == 2
    (pn, gn), (pt, gt) = _props(rows[0]), _props(rows[1])
    assert gn("글 번호") == "N-008" and gt("글 번호") == "T-008"
    assert pn["채널"]["select"]["name"] == "네이버 블로그" and pt["채널"]["select"]["name"] == "티스토리"
    assert pn["타깃"]["select"]["name"] == "반의사"            # 병원 → 반의사 형식
    assert gn("대상 질문").startswith("GQ-4 ")
    assert pn["질문 의도"]["select"]["name"] == "정보"
    assert pn["원천 기사"]["url"] == "https://news.example/1"
    assert gn("흥미도 점수") == "70점 (A25 B20 C8 D10 E5 F2)"
    assert gn("담당") == "웅서" and pn["상태"]["select"]["name"] == "근거수집"
    assert gn("제목") == "병원에서 의사를 빨리 채용하는 방법은?"   # 기사 제목을 쓰지 않음
    log = gn("작업 기록")
    assert "원고 설계" in log and "피할 점" in log and "DR-MKT-02" in log and "abcd1234" in log
    assert "울산" not in log


def test_evergreen_single_channel_has_no_article():
    c = g3.from_page(_page(kind="상록 슬롯", channel="티스토리", question="GQ-6 의사 헤드헌팅과 매칭 플랫폼은 뭐가 달라?",
                           target="공통", total=None, url="", marks=()))
    (row,) = g3.rows_for(c, 9, date(2026, 10, 28), "db")
    p, get = _props(row)
    assert get("글 번호") == "T-009" and "원천 기사" not in p
    assert get("흥미도 점수") == "상록" and p["질문 의도"]["select"]["name"] == "비교"
    assert p["타깃"]["select"]["name"] == "의사"


def test_no_question_makes_no_row():
    c = g3.from_page(_page(question="없음 → 좋은 기사면 G1 새 질문 후보"))
    assert g3.rows_for(c, 8, date(2026, 10, 28), "db") == []


def test_reviewer_rotation_skips_owner():
    assert g3.reviewer(date(2026, 10, 22))[0] == "세현"    # 1주차 리뷰어 웅서 = 담당 → 블로그 순번 세현
    assert g3.reviewer(date(2026, 10, 28)) == ("세현", "")  # 2주차
    assert g3.reviewer(date(2026, 11, 3)) == ("모세", "")   # 3주차


def test_next_number_and_intent():
    assert g3.next_number(["N-007", "T-007", "T-001", "N-20261026-0001", ""]) == 8
    assert g3.intent("닥터온 수수료는 얼마야?") == "브랜드"


def test_run_creates_rows_and_marks_candidate(monkeypatch):
    calls = []

    def fake(method, url, payload=None, headers=None, timeout=0):
        calls.append((method, url, payload))
        if url.endswith("/query"):
            if "5c99c33b" in url:
                return {"results": [_page()]}
            return {"results": [{"properties": {"글 번호": {"type": "title", "title": [{"plain_text": "N-007"}]}},
                                 "created_time": "2026-10-26T15:07:15Z"}]}
        return {}

    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(g3._http, "request_json", fake)
    out = g3.run(datetime(2026, 10, 28, 11, 7, tzinfo=KST), pause=0)
    posts = [p for m, u, p in calls if m == "POST" and u.endswith("/pages")]
    assert len(posts) == 2
    mark = [p for m, u, p in calls if m == "PATCH"]
    assert mark[0]["properties"]["체인 글 번호"]["rich_text"][0]["text"]["content"] == "N-008, T-008"
    assert "N-008, T-008" in out[1]


def test_run_skips_when_row_already_made(monkeypatch):
    calls = []

    def fake(method, url, payload=None, headers=None, timeout=0):
        calls.append((method, url))
        if url.endswith("/query"):
            if "5c99c33b" in url:
                return {"results": [_page()]}
            return {"results": [{"properties": {
                "글 번호": {"type": "title", "title": [{"plain_text": "N-008"}]},
                "작업 기록": {"type": "rich_text", "rich_text": [{"plain_text": "10/28 G3 세현 선택 (뉴스 · 후보 2026-10-27 abcd1234)"}]}}}]}
        return {}

    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(g3._http, "request_json", fake)
    g3.run(datetime(2026, 10, 28, tzinfo=KST), pause=0)
    assert not [u for m, u in calls if m == "POST" and u.endswith("/pages")]
    assert [m for m, u in calls if m == "PATCH"] == ["PATCH"]
