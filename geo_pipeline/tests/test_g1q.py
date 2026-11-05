from datetime import datetime

import pytest

from pipeline import g1q, g2
from pipeline.sources.news import KST

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=KST)


@pytest.fixture(autouse=True)
def keep_questions():
    saved = list(g2.QUESTIONS)
    yield
    g2.QUESTIONS[:] = saved
    g2.BY_ID.clear()
    g2.BY_ID.update({q.gq: q for q in saved})


def item(url, title, desc=""):
    return {"title": title, "description": desc, "originallink": url, "link": "https://n.news.naver.com/x"}


Q3 = g2.BY_ID[3]   # 봉직의 연봉 정보 — 근거 필요, 매칭 단어 '봉직의 연봉'


def test_judge_needs_three_outlets_and_one_trusted():
    items = [
        item("https://www.doctorsnews.co.kr/a", "<b>봉직의 연봉</b> 조사"),
        item("https://news.example.com/b", "봉직의 연봉 오른다"),
        item("https://daily.example.kr/c", "페이닥터 연봉 비교"),
    ]
    v = g1q.judge(Q3, items)
    assert v.passed and v.trusted == ["doctorsnews.co.kr"] and len(v.domains) == 3
    assert v.urls[0].startswith("https://www.doctorsnews")   # 전문지 출처가 먼저


def test_judge_fails_without_trusted_or_with_unrelated():
    general = [item(f"https://n{i}.example.com/x", "봉직의 연봉") for i in range(5)]
    assert not g1q.judge(Q3, general).passed                    # 일반 언론만
    unrelated = [item("https://www.doctorsnews.co.kr/a", "전공의 복귀")] + general[:2]
    assert not g1q.judge(Q3, unrelated).passed                  # 전문지 기사가 질문과 무관
    same = [item("https://www.hira.or.kr/a", "봉직의 연봉")] + [item("https://a.example.com/" + str(i), "봉직의 연봉") for i in range(3)]
    v = g1q.judge(Q3, same)
    assert len(v.domains) == 2 and not v.passed                 # 같은 도메인은 한 곳으로


def test_eligible_rules():
    row = g1q.BankRow(3, "p3", "근거 필요", "")
    assert g1q.eligible(Q3, row, set(), NOW)
    assert not g1q.eligible(Q3, row, {3}, NOW)                                         # 이미 글 있음
    assert not g1q.eligible(Q3, g1q.BankRow(3, "p", "근거 필요", "세현: 검수 제외"), set(), NOW)
    recent = g1q.BankRow(3, "p", "근거 필요", "2026-11-01 G1-Q 검수 미달 · 근거 1곳")
    assert not g1q.eligible(Q3, recent, set(), NOW)                                    # 7일 안 미달
    old = g1q.BankRow(3, "p", "근거 필요", "2026-10-20 G1-Q 검수 미달 · 근거 1곳")
    assert g1q.eligible(Q3, old, set(), NOW)
    assert not g1q.eligible(g2.BY_ID[5], None, set(), NOW)                             # 확정값 필요
    assert not g1q.eligible(g2.BY_ID[2], None, set(), NOW)                             # 닥터온 질문


def test_apply_bank_overrides_ready_and_plan_orders_p1_first():
    rows = {3: g1q.BankRow(3, "p3", "바로 가능", ""), 6: g1q.BankRow(6, "p6", "근거 필요", "")}
    assert sorted(g1q.apply_bank(rows)) == [3, 6]
    assert g2.BY_ID[3].ready == "바로 가능" and g2.BY_ID[6].ready == "근거 필요"
    written = {q.gq for q in g2.QUESTIONS if q.ready == "바로 가능"}   # 재고 0
    need, todo = g1q.plan(written, {}, NOW)
    assert need == g2.REFILL_AT and todo
    pr = [g2.PRIORITY_ORDER[q.priority] for q in todo]
    assert pr == sorted(pr) and all(q.ready == "근거 필요" for q in todo)


def test_run_promotes_until_stock_and_reports_hold(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "x")
    written = {q.gq for q in g2.QUESTIONS if q.ready == "바로 가능"}
    bank = [q for q in g2.QUESTIONS if q.ready == "근거 필요"]
    rows = {q.gq: g1q.BankRow(q.gq, f"page{q.gq}", q.ready, "") for q in g2.QUESTIONS}
    monkeypatch.setattr(g1q, "load_bank", lambda h, db: rows)
    good = lambda q: [item(u, q.terms[0]) for u in
                      ("https://www.dailymedi.com/1", "https://a.example.com/1", "https://b.example.com/1")]
    monkeypatch.setattr(g1q, "search_news", lambda c, q: good(q))
    patched = []
    monkeypatch.setattr(g1q._http, "request_json", lambda m, url, body, headers: patched.append((url, body)) or {})
    out = g1q.run(None, NOW, written)
    assert len(patched) == g2.REFILL_AT                               # 재고 5개가 될 때까지만
    assert all(b["properties"]["답 준비도"]["select"]["name"] == "바로 가능" for _, b in patched)
    assert "G1-Q 검수 통과" in patched[0][1]["properties"]["메모"]["rich_text"][0]["text"]["content"]
    assert len(g2.ready_left(written)) == g2.REFILL_AT
    holds = [ln for ln in out if ln.startswith("⏸")]
    assert len(holds) == 1 and "자동 승격" in holds[0] and "담당: 세현" in holds[0]
    assert len(bank) > g2.REFILL_AT


def test_run_dry_run_writes_nothing(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "x")
    written = {q.gq for q in g2.QUESTIONS if q.ready == "바로 가능"}
    monkeypatch.setattr(g1q, "load_bank", lambda h, db: {})
    monkeypatch.setattr(g1q, "search_news", lambda c, q: [])
    monkeypatch.setattr(g1q._http, "request_json", lambda *a, **k: pytest.fail("쓰면 안 됨"))
    out = g1q.run(None, NOW, written, dry_run=True)
    assert any("미달" in ln for ln in out) and not any(ln.startswith("⏸") for ln in out)


def test_run_bank_read_failure_falls_back(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "x")

    def boom(h, db):
        e = Exception("nf"); e.code = 404; raise e
    monkeypatch.setattr(g1q, "load_bank", boom)
    out = g1q.run(None, NOW, set())
    assert out[0].startswith("⏸ [G1-Q] 질문 은행 읽기 실패(404)")


def test_cli_has_g1q_command(monkeypatch, capsys):
    from pipeline import cli   # cli.py 문법 오류를 테스트에서 잡으려고 (11/5 줄바꿈 사고)

    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    cli.main(["g1q", "--dry-run"])
    assert "G1-Q" in capsys.readouterr().out
