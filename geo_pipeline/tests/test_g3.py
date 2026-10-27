"""G3 선택 → 체인 DB 행 테스트 (네트워크 불필요)."""

from __future__ import annotations

from datetime import date, datetime

from pipeline import g3
from pipeline.sources.news import KST


def _page(pid="abcd1234-0000", kind="뉴스", channel="둘 다", question="GQ-4 병원에서 의사를 빨리 채용하는 방법은?",
          target="병원", total=70, url="https://news.example/1", marks=("논쟁",), rank=1, checked=False, no=""):
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
        "순위": {"type": "number", "number": rank},
        "선택": {"type": "checkbox", "checkbox": checked},
        "체인 글 번호": t(no),
    }}


def _props(row):
    p = row["properties"]
    get = lambda k: "".join(x["text"]["content"] for x in p[k].get("rich_text", p[k].get("title", [])))
    return p, get


def test_news_row_has_required_fields():
    c = g3.from_page(_page())
    p, get = _props(g3.row_for(c, "N", 8, date(2026, 10, 28), "db"))
    assert get("글 번호") == "N-008" and p["채널"]["select"]["name"] == "네이버 블로그"
    assert p["타깃"]["select"]["name"] == "반의사"            # 병원 → 반의사 형식
    assert get("대상 질문").startswith("GQ-4 ")
    assert p["질문 의도"]["select"]["name"] == "정보"
    assert p["원천 기사"]["url"] == "https://news.example/1"
    assert get("흥미도 점수") == "70점 (A25 B20 C8 D10 E5 F2)"
    assert get("담당") == "웅서" and p["상태"]["select"]["name"] == "근거수집"
    assert get("제목") == "병원에서 의사를 빨리 채용하는 방법은?"   # 기사 제목을 쓰지 않음
    log = get("작업 기록")
    assert "자동 선택 1등" in log and "원고 설계" in log and "DR-MKT-02" in log and "abcd1234" in log
    assert "울산" not in log


def test_evergreen_row_has_no_article():
    c = g3.from_page(_page(kind="상록 슬롯", channel="티스토리", question="GQ-6 의사 헤드헌팅과 매칭 플랫폼은 뭐가 달라?",
                           target="공통", total=None, url="", marks=()))
    p, get = _props(g3.row_for(c, "T", 9, date(2026, 10, 28), "db"))
    assert get("글 번호") == "T-009" and "원천 기사" not in p
    assert get("흥미도 점수") == "상록" and p["질문 의도"]["select"]["name"] == "비교"
    assert p["타깃"]["select"]["name"] == "의사"


def test_choose_top2_with_question_or_checked():
    a = g3.from_page(_page("a", rank=1))
    b = g3.from_page(_page("b", rank=2, question="없음 → 좋은 기사면 G1 새 질문 후보"))
    c = g3.from_page(_page("c", rank=3))
    d = g3.from_page(_page("d", rank=4, checked=True))
    assert [x.page_id for x in g3.choose([c, b, a])] == ["a", "c"]   # GQ 없는 2등은 건너뜀
    assert [x.page_id for x in g3.choose([a, c, d])] == ["d"]        # 사람이 체크했으면 그것
    assert g3.row_for(b, "N", 8, date(2026, 10, 28), "db") is None


def test_channels_pair():
    mk = lambda ch: g3.from_page(_page(channel=ch))
    assert g3.channels([mk("티스토리"), mk("티스토리")]) == ["T", "N"]
    assert g3.channels([mk("둘 다"), mk("티스토리")]) == ["N", "T"]
    assert g3.channels([mk("둘 다"), mk("네이버")]) == ["T", "N"]
    assert g3.channels([mk("둘 다")]) == ["N"]


def test_reviewer_rotation_skips_owner():
    assert g3.reviewer(date(2026, 10, 22))[0] == "세현"    # 1주차 리뷰어 웅서 = 담당 → 블로그 순번 세현
    assert g3.reviewer(date(2026, 10, 28)) == ("세현", "")  # 2주차
    assert g3.reviewer(date(2026, 11, 3)) == ("모세", "")   # 3주차


def test_next_number_and_intent():
    assert g3.next_number(["N-007", "T-007", "T-001", "N-20261026-0001", ""]) == 8
    assert g3.intent("닥터온 수수료는 얼마야?") == "브랜드"


def _fake(calls, cands, chain):
    def fake(method, url, payload=None, headers=None, timeout=0):
        calls.append((method, url, payload))
        if url.endswith("/query"):
            return {"results": cands if "5c99c33b" in url else chain}
        return {}
    return fake


def test_run_auto_picks_top2_as_pair(monkeypatch):
    calls = []
    chain = [{"properties": {"글 번호": {"type": "title", "title": [{"plain_text": "N-007"}]}},
              "created_time": "2026-10-26T15:07:15Z"}]
    cands = [_page("a1", rank=1, channel="티스토리"), _page("b2", rank=2), _page("c3", rank=3)]
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(g3._http, "request_json", _fake(calls, cands, chain))
    out = g3.run(datetime(2026, 10, 28, 14, 50, tzinfo=KST), pause=0)
    posts = [p for m, u, p in calls if m == "POST" and u.endswith("/pages")]
    assert [p["properties"]["글 번호"]["title"][0]["text"]["content"] for p in posts] == ["T-008", "N-008"]
    marks = [(u.rsplit("/", 1)[1], p["properties"]) for m, u, p in calls if m == "PATCH"]
    assert [m[0] for m in marks] == ["a1", "b2"]
    assert marks[0][1]["선택"]["checkbox"] is True
    assert marks[0][1]["체인 글 번호"]["rich_text"][0]["text"]["content"] == "T-008"
    assert "T-008" in out[1] and "N-008" in out[2]


def test_run_skips_day_already_handed_over(monkeypatch):
    calls = []
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(g3._http, "request_json", _fake(calls, [_page(no="N-008"), _page("b2", rank=2)], []))
    out = g3.run(datetime(2026, 10, 28, tzinfo=KST), pause=0)
    assert not [m for m, u, p in calls if m in ("PATCH",) or (m == "POST" and u.endswith("/pages"))]
    assert "이미 넘김" in out[-1]


def test_run_resumes_half_done_with_same_number(monkeypatch):
    calls = []
    chain = [{"properties": {
        "글 번호": {"type": "title", "title": [{"plain_text": "T-008"}]},
        "작업 기록": {"type": "rich_text", "rich_text": [{"plain_text": "10/28 G3 자동 선택 1등 (뉴스 · 후보 2026-10-28 a1)"}]}}}]
    cands = [_page("a1", rank=1, channel="티스토리"), _page("b2", rank=2)]
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(g3._http, "request_json", _fake(calls, cands, chain))
    g3.run(datetime(2026, 10, 28, tzinfo=KST), pause=0)
    posts = [p for m, u, p in calls if m == "POST" and u.endswith("/pages")]
    assert [p["properties"]["글 번호"]["title"][0]["text"]["content"] for p in posts] == ["N-008"]
