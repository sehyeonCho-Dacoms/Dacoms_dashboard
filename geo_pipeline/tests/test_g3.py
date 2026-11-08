"""G3 선택 → 체인 DB 행 테스트 (네트워크 불필요). 준칙 v2 (11/8): 평일 트랙 · 주제 1개 = N 행 1개."""

from __future__ import annotations

from datetime import date, datetime

from pipeline import g3
from pipeline.sources.news import KST


def _page(pid="abcd1234-0000", kind="뉴스", channel="둘 다", question="GQ-4 병원에서 의사를 빨리 채용하는 방법은?",
          target="병원", total=70, url="https://news.example/1", marks=("논쟁",), rank=1, checked=False, no="",
          track="채용·의사 일"):
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
        "트랙": {"type": "select", "select": {"name": track}},
    }}


def _props(row):
    p = row["properties"]
    get = lambda k: "".join(x["text"]["content"] for x in p[k].get("rich_text", p[k].get("title", [])))
    return p, get


def test_news_row_has_required_fields():
    c = g3.from_page(_page())
    p, get = _props(g3.row_for(c, 8, date(2026, 10, 28), "db"))
    assert get("글 번호") == "N-008" and p["채널"]["select"]["name"] == "네이버 블로그"
    assert p["트랙"]["select"]["name"] == "채용·의사 일"
    assert p["타깃"]["select"]["name"] == "반의사"            # 병원 → 반의사 형식
    assert get("대상 질문").startswith("GQ-4 ")
    assert p["질문 의도"]["select"]["name"] == "하는 법"      # v2: '방법' → 하는 법
    assert p["원천 기사"]["url"] == "https://news.example/1"
    assert get("흥미도 점수") == "70점 (A25 B20 C8 D10 E5 F2)"
    assert get("담당") == "웅서" and p["상태"]["select"]["name"] == "근거수집"
    assert get("제목") == "병원에서 의사를 빨리 채용하는 방법은?"   # 기사 제목을 쓰지 않음
    log = get("작업 기록")
    assert "자동 선택 1등" in log and "원고 설계" in log and "DR-MKT-02" in log and "abcd1234" in log
    assert "티스토리" in log and "80%" in log and "원고 규칙 v2" in log and "내부 링크 금지(11/9 전)" in log
    assert "울산" not in log


def test_evergreen_row_has_no_article():
    c = g3.from_page(_page(kind="상록 슬롯", channel="티스토리", question="GQ-6 의사 헤드헌팅과 매칭 플랫폼은 뭐가 달라?",
                           target="공통", total=None, url="", marks=()))
    p, get = _props(g3.row_for(c, 9, date(2026, 11, 10), "db"))
    assert get("글 번호") == "N-009" and "원천 기사" not in p
    assert get("흥미도 점수") == "상록" and p["질문 의도"]["select"]["name"] == "비교"
    assert p["타깃"]["select"]["name"] == "의사"
    assert "내부 링크: 채용 글 1~2개" in get("작업 기록")      # 11/9 오픈 뒤 규칙


def test_medical_news_row_without_question():
    c = g3.from_page(_page(question="없음 → 좋은 기사면 G1 새 질문 후보", track="의료 뉴스", marks=("의료", "근거 확인")))
    p, get = _props(g3.row_for(c, 20, date(2026, 11, 9), "db"))
    assert p["트랙"]["select"]["name"] == "의료 뉴스" and get("대상 질문").startswith("뉴스 · ")
    assert get("제목").startswith("(가제) ")
    log = get("작업 기록")
    assert "의료 조언" in log and "근거 부족 되돌림" in log and "누구에게 무엇이 달라지나" in log


def test_choose_by_day_track_checked_and_fallback():
    job = g3.from_page(_page("j", rank=1))
    noq = g3.from_page(_page("q", rank=2, question="없음 → 좋은 기사면 G1 새 질문 후보"))
    news = g3.from_page(_page("n", rank=1, question="없음", track="의료 뉴스"))
    chk = g3.from_page(_page("c", rank=3, checked=True))
    assert [x.page_id for x in g3.choose([noq, job, news], "의료 뉴스")] == ["n"]
    assert [x.page_id for x in g3.choose([noq, job, news], "채용·의사 일")] == ["j"]
    assert [x.page_id for x in g3.choose([noq, job], "의료 뉴스")] == ["j"]          # 뉴스 없으면 채용으로
    assert [x.page_id for x in g3.choose([job, news, chk], "의료 뉴스")] == ["c"]    # 사람이 체크했으면 그것
    assert g3.row_for(noq, 8, date(2026, 10, 28), "db") is None                    # 채용 후보는 GQ 필수


def test_day_track_weekdays_only():
    assert g3.day_track(date(2026, 11, 9)) == "의료 뉴스"     # 월
    assert g3.day_track(date(2026, 11, 10)) == "채용·의사 일"  # 화
    assert g3.day_track(date(2026, 11, 14)) is None           # 토


def test_reviewer_rotation_skips_owner():
    assert g3.reviewer(date(2026, 10, 22))[0] == "세현"    # 1주차 리뷰어 웅서 = 담당 → 블로그 순번 세현
    assert g3.reviewer(date(2026, 10, 28)) == ("세현", "")  # 2주차
    assert g3.reviewer(date(2026, 11, 3)) == ("모세", "")   # 3주차
    assert g3.reviewer(date(2026, 11, 17)) == ("세현", "")  # 5주차 (v2 표 연장)


def test_next_number_and_intent():
    assert g3.next_number(["N-007", "T-007", "T-001", "N-20261026-0001", ""]) == 8
    assert g3.intent("닥터온 수수료는 얼마야?") == "브랜드"
    assert g3.intent("봉직의 근로계약서에서 꼭 확인할 조항은?") == "하는 법"


def _fake(calls, cands, chain):
    def fake(method, url, payload=None, headers=None, timeout=0):
        calls.append((method, url, payload))
        if url.endswith("/query"):
            return {"results": cands if "5c99c33b" in url else chain}
        return {}
    return fake


def _numbers(calls):
    return [p["properties"]["글 번호"]["title"][0]["text"]["content"]
            for m, u, p in calls if m == "POST" and u.endswith("/pages")]


def test_run_one_topic_one_n_row(monkeypatch):
    """v2: 주제 1개 = N 행 1개(티스토리판 포함). T 행은 만들지 않는다. 화요일 = 채용·의사 일."""
    calls = []
    chain = [{"properties": {"글 번호": {"type": "title", "title": [{"plain_text": "T-015"}]}},
              "created_time": "2026-11-06T15:07:15Z"}]
    cands = [_page("a1", rank=1, channel="티스토리"), _page("b2", rank=2), _page("n1", rank=1, track="의료 뉴스")]
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(g3._http, "request_json", _fake(calls, cands, chain))
    out = g3.run(datetime(2026, 11, 10, 14, 50, tzinfo=KST), pause=0)
    assert _numbers(calls) == ["N-016"]
    marks = [(u.rsplit("/", 1)[1], p["properties"]) for m, u, p in calls if m == "PATCH"]
    assert [m[0] for m in marks] == ["a1"]
    assert marks[0][1]["체인 글 번호"]["rich_text"][0]["text"]["content"] == "N-016"
    assert "채용·의사 일 날" in out[0] and "N-016" in out[1]


def test_run_news_day_picks_news_track(monkeypatch):
    calls = []
    cands = [_page("a1", rank=1), _page("n1", rank=1, question="없음", track="의료 뉴스")]
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(g3._http, "request_json", _fake(calls, cands, []))
    g3.run(datetime(2026, 11, 11, 14, 50, tzinfo=KST), pause=0)   # 수
    posts = [p for m, u, p in calls if m == "POST" and u.endswith("/pages")]
    assert len(posts) == 1 and posts[0]["properties"]["트랙"]["select"]["name"] == "의료 뉴스"


def test_run_weekend_makes_nothing(monkeypatch):
    calls = []
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(g3._http, "request_json", _fake(calls, [_page()], []))
    out = g3.run(datetime(2026, 11, 14, 14, 50, tzinfo=KST), pause=0)
    assert not calls and "주말" in out[0] and not any("❌" in x for x in out)


def test_run_skips_day_already_handed_over(monkeypatch):
    calls = []
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(g3._http, "request_json", _fake(calls, [_page(no="N-008"), _page("b2", rank=2)], []))
    out = g3.run(datetime(2026, 10, 28, tzinfo=KST), pause=0)
    assert not [m for m, u, p in calls if m in ("PATCH",) or (m == "POST" and u.endswith("/pages"))]
    assert "이미 넘김" in out[-1]


def test_run_resumes_half_done_without_new_row(monkeypatch):
    calls = []
    chain = [{"properties": {
        "글 번호": {"type": "title", "title": [{"plain_text": "N-016"}]},
        "작업 기록": {"type": "rich_text", "rich_text": [{"plain_text": "11/10 G3 자동 선택 1등 (뉴스 · 후보 2026-11-10 a1)"}]}}}]
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(g3._http, "request_json", _fake(calls, [_page("a1", rank=1)], chain))
    g3.run(datetime(2026, 11, 10, tzinfo=KST), pause=0)
    assert _numbers(calls) == []
    assert [u.rsplit("/", 1)[1] for m, u, p in calls if m == "PATCH"] == ["a1"]


def test_no_candidates_fails_after_safety_net_hour(monkeypatch):
    """D-026: 16시 이후에도 후보가 없으면 ❌ (예전엔 초록으로 끝나 10/30에 아무도 몰랐음)."""
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(g3._http, "request_json", _fake([], [], []))
    early = g3.run(datetime(2026, 11, 5, 14, 50, tzinfo=KST), pause=0)
    late = g3.run(datetime(2026, 11, 5, 16, 40, tzinfo=KST), pause=0)
    assert not any("❌" in x for x in early)
    assert any(x.startswith("❌") for x in late) and any(x.startswith("⏸ [G2→G3]") for x in late)


def test_candidates_without_question_fail(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setattr(g3._http, "request_json", _fake([], [_page("a1", question="없음 → 새 질문 후보")], []))
    out = g3.run(datetime(2026, 11, 5, 14, 50, tzinfo=KST), pause=0)
    assert any(x.startswith("❌") for x in out) and any("⏸ [G1→G3]" in x for x in out)
