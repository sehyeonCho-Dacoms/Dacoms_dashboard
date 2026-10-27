"""G3 선택 → 체인 DB 글 행 (DR-GEO-02, 10/27 통합 인수인계 2장).

G2가 그날 'G2 오늘의 후보' DB에 후보를 올리면, **점수 1·2등을 자동 선택**해(10/27 세현 결정) '블로그 GEO 체인'
DB에 글 행을 만들고 상태를 '근거수집'으로 둔다. 이 행이 웅서(G4~G11)에게 넘기는 유일한 연결 고리다.

- 하루 = 같은 번호의 N-·T- 한 쌍(기존 N-002/T-002처럼 주제는 서로 다름). 1등이 원하는 채널을 먼저 갖고 2등이 나머지.
- 16:37 자동 실행(G2 후보는 실제 14시대) 전에 사람이 '선택'을 체크해 두었으면 그 후보를 쓴다. 상록 슬롯도 순위대로 후보.
- 그날 후보 중 하나라도 '체인 글 번호'가 있으면 그날은 끝난 것으로 보고 건너뛴다. 지난 날짜는 손대지 않는다.

- 2장 필수 칸을 모두 채운다: 글 번호 · 제목(가제목) · 채널 · 타깃 · 대상 질문(GQ-n) · 질문 의도 ·
  원천 기사(뉴스만) · 흥미도 점수 · 담당(웅서) · 리뷰어(로테이션) · 작업 기록(고른 이유 + 원고 설계) · 상태.
- 매칭 질문(GQ)이 없는 후보는 고르지 않는다(14일 중복 규칙이 안 돌아감) → 다음 순위로.
- 고른 후보는 '선택' 체크 + '체인 글 번호'를 적는다.
- 행을 만든 뒤에는 2장 칸만 고친다(3장 칸은 웅서). 기사 본문·요약은 넣지 않는다(RULE-11).
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import _http
from .g2 import BY_ID
from .notion import DEFAULT_DB, VERSION, _text
from .notion_g0 import DEFAULT_G2_DB

API = "https://api.notion.com/v1"
STAGE = "근거수집"
OWNER = "웅서"
PICKS = 2
PREF = {"티스토리": "T", "네이버": "N"}   # 둘 다 → 정하지 않음
CHANNEL = {"N": "네이버 블로그", "T": "티스토리"}
# 체인 DB 타깃은 의사/반의사 두 칸뿐. 병원(원장·인사 담당)은 반의사 형식, 공통은 의사 형식으로 쓴다.
TARGET = {"의사": "의사", "반의사": "반의사", "병원": "반의사", "공통": "의사"}

# 로테이션 (부모 페이지 '로테이션' 표). 1주차 = 10/19 주. 통합 후 블로그 담당은 웅서로 고정이라
# 리뷰어가 웅서가 되는 주에는 그 주 블로그 담당(원래 글 쓸 사람)이 리뷰를 맡는다.
WEEK1 = date(2026, 10, 19)
ROTATION = [("세현", "웅서"), ("모세", "세현"), ("웅서", "모세")]   # (블로그, 리뷰어)

# 원고 설계: 부모 페이지 '원고 형식(타깃 2 × 채널 2)' 표 + G5 준칙(소제목 3~5·FAQ) + G-R 2026-10 측정.
# G-R 월간 결과로 표가 바뀌면 여기도 고친다.
FORMAT = {
    ("의사", "N"): "소제목 3~5(질문형) · 표 1(연봉·조건) · FAQ 2~3 · 현장 사례는 익명",
    ("의사", "T"): "H2 소제목 3~5 · 비교표 1 이상 · FAQ 3 · 수치마다 출처 링크·날짜",
    ("반의사", "N"): "소제목 3 · 실무 팁·체크리스트 · 짧은 문단 · FAQ 2",
    ("반의사", "T"): "H2 소제목 3~4 · 절차표 1 · 체크리스트 · FAQ 2 · 출처 링크",
}
AVOID = "기사 문장·순서 따라 쓰기 금지(RULE-11) · 닥터온 내부 링크 금지(11/9 전) · 닥터온 수치는 허브 확정값만"


@dataclass
class Candidate:
    page_id: str
    title: str
    day: str
    kind: str          # 뉴스 / 상록 슬롯
    total: int | None
    breakdown: str
    target: str
    channel: str
    question: str      # "GQ-n 질문" 또는 "없음 → ..."
    url: str
    marks: list[str]
    reason: str
    memo: str
    rank: int = 0
    checked: bool = False
    chain_no: str = ""

    @property
    def gq(self) -> int | None:
        m = re.match(r"\s*GQ-(\d+)", self.question)
        return int(m.group(1)) if m else None

    @property
    def news(self) -> bool:
        return self.kind == "뉴스"


def _plain(p: dict) -> str:
    kind = p.get("type")
    if kind in ("title", "rich_text"):
        return "".join(t.get("plain_text", "") for t in p.get(kind, []))
    if kind == "select":
        return (p.get("select") or {}).get("name", "")
    if kind == "url":
        return p.get("url") or ""
    if kind == "date":
        return (p.get("date") or {}).get("start", "")
    if kind == "number":
        return "" if p.get("number") is None else str(p["number"])
    return ""


def from_page(page: dict) -> Candidate:
    p = page.get("properties", {})
    g = lambda k: _plain(p.get(k, {}))
    total = g("총점")
    return Candidate(
        page_id=page["id"], title=g("후보"), day=g("날짜")[:10], kind=g("종류"),
        total=int(float(total)) if total else None, breakdown=g("점수 내역"), target=g("타깃"),
        channel=g("채널") or "둘 다", question=g("매칭 질문"), url=g("원천 기사"),
        marks=[m["name"] for m in p.get("표시", {}).get("multi_select", [])], reason=g("한 줄 이유"), memo=g("메모"),
        rank=int(float(g("순위") or 0)), checked=bool(p.get("선택", {}).get("checkbox")), chain_no=g("체인 글 번호"))


def choose(cands: list[Candidate]) -> list[Candidate]:
    """사람이 체크한 후보가 있으면 그것, 없으면 GQ가 있는 후보 중 순위 1·2등."""
    ok = sorted((c for c in cands if c.gq in BY_ID), key=lambda c: c.rank or 99)
    return ([c for c in ok if c.checked] or ok)[:PICKS]


def channels(picks: list[Candidate]) -> list[str]:
    """하루 N·T 한 쌍: 1등이 원하는 채널, 2등이 나머지. 1등이 '둘 다'면 2등이 원하는 채널을 양보받는다."""
    if not picks:
        return []
    first = PREF.get(picks[0].channel)
    if len(picks) == 1:
        return [first or "N"]
    if not first:
        first = "T" if PREF.get(picks[1].channel) == "N" else "N"
    return [first, "T" if first == "N" else "N"]


def intent(text: str) -> str:
    if "닥터온" in text:
        return "브랜드"
    if re.search(r"달라|차이|vs|비교", text):
        return "비교"
    return "정보"


def reviewer(day: date) -> tuple[str, str]:
    """(리뷰어, 메모). 1주차 = 10/19 주, 3주 주기."""
    blog, rev = ROTATION[((day - WEEK1).days // 7) % len(ROTATION)]
    if rev == OWNER:
        return blog, f"로테이션 리뷰어가 담당({OWNER})과 같아 이번 주 블로그 순번 {blog}이 리뷰"
    return rev, ""


def next_number(existing: list[str]) -> int:
    nums = [int(m.group(1)) for no in existing if (m := re.match(r"[NT]-(\d+)$", no.strip()))]
    return max(nums, default=0) + 1


def score_text(c: Candidate) -> str:
    if not c.news or c.total is None:
        return "상록"
    return f"{c.total}점 ({c.breakdown})" if c.breakdown else f"{c.total}점"


def work_log(c: Candidate, target: str, prefix: str, today: date, note: str) -> str:
    why = c.reason or ("상록 슬롯" if not c.news else "")
    must = f"첫 문단에서 GQ-{c.gq} 질문에 바로 답" + (f" · {c.memo}" if c.memo else "")
    avoid = AVOID + (" · 논쟁/법률 표시 → 입장은 사람이 정함(DR-MKT-02)" if c.marks else "")
    how = "사람 선택" if c.checked else f"자동 선택 {c.rank}등"
    head = f"{today:%m/%d} G3 {how} ({c.kind} · 후보 {c.day} {c.page_id[:8]})"
    parts = [head, f"고른 이유: {why}" if why else "",
             f"원고 설계(G-R 형식표): {FORMAT[(target, prefix)]}", f"꼭 다룰 점: {must}", f"피할 점: {avoid}", note]
    return "\n".join(x for x in parts if x)


def row_for(c: Candidate, prefix: str, number: int, today: date, db: str) -> dict | None:
    """후보 1건 → 체인 DB 행 1개. GQ가 없으면 None."""
    q = BY_ID.get(c.gq) if c.gq else None
    if not q:
        return None
    target = TARGET.get(c.target or q.target, "의사")
    rev, note = reviewer(today)
    props = {
        "글 번호": {"title": _text(f"{prefix}-{number:03d}")},
        "제목": {"rich_text": _text(q.text)},   # 가제목 = 질문(기사 제목은 쓰지 않음). 웅서가 바꾸면 작업 기록에
        "채널": {"select": {"name": CHANNEL[prefix]}},
        "타깃": {"select": {"name": target}},
        "대상 질문": {"rich_text": _text(f"GQ-{q.gq} {q.text} ({q.priority} · {q.evergreen} · {q.ready})")},
        "질문 의도": {"select": {"name": intent(q.text)}},
        "흥미도 점수": {"rich_text": _text(score_text(c))},
        "담당": {"rich_text": _text(OWNER)},
        "리뷰어": {"rich_text": _text(rev)},
        "작업 기록": {"rich_text": _text(work_log(c, target, prefix, today, note))},
        "상태": {"select": {"name": STAGE}},
    }
    if c.news and c.url:
        props["원천 기사"] = {"url": c.url}
    return {"parent": {"database_id": db}, "properties": props}


# --------------------------------------------------------------------------- #
# 노션 읽기·쓰기
# --------------------------------------------------------------------------- #
def _query(db: str, body: dict, h: dict) -> list[dict]:
    out, body = [], {"page_size": 100, **body}
    while True:
        res = _http.request_json("POST", f"{API}/databases/{db}/query", body, headers=h)
        out += res.get("results", [])
        if not res.get("has_more"):
            return out
        body["start_cursor"] = res["next_cursor"]


def day_candidates(g2_db: str, day: str, h: dict) -> list[Candidate]:
    pages = _query(g2_db, {"filter": {"property": "날짜", "date": {"equals": day}},
                           "sorts": [{"property": "순위", "direction": "ascending"}]}, h)
    return [from_page(p) for p in pages]


def week_balance(chain: list[dict], today: date) -> str:
    """이번 주(월~) 체인 행의 뉴스형·타깃 수 — 주간 균형(뉴스형 주 1편, 의사 1 + 병원·반의사 1) 확인용."""
    monday = (today - timedelta(days=today.weekday())).isoformat()
    rows = [r for r in chain if r.get("created_time", "") >= monday]
    p = lambda r, k: _plain(r.get("properties", {}).get(k, {}))
    news = sum(1 for r in rows if p(r, "원천 기사"))
    doc = sum(1 for r in rows if p(r, "타깃") == "의사")
    semi = sum(1 for r in rows if p(r, "타깃") == "반의사")
    return f"이번 주 글 행 {len(rows)}개 · 뉴스형 {news} · 의사 {doc} · 반의사(병원 포함) {semi} (목표: 뉴스형 주 1, 의사 1 + 병원·반의사 1)"


def run(now: datetime, dry_run: bool = False, pause: float = 0.35, day: str | None = None) -> list[str]:
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return ["   G3: NOTION_TOKEN 이 없어 건너뜀"]
    h = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}
    db = os.getenv("NOTION_GEO_DB", DEFAULT_DB)
    g2_db = os.getenv("NOTION_G2_DB", DEFAULT_G2_DB)
    day = day or now.strftime("%Y-%m-%d")
    try:
        cands = day_candidates(g2_db, day, h)
        chain = _query(db, {}, h)
    except Exception as exc:
        code = getattr(exc, "code", "")
        hint = {404: "DB에 통합이 연결되지 않음", 401: "토큰 오류",
                400: "후보 DB에 '체인 글 번호' 칸이 있는지 확인"}.get(code, str(exc))
        return [f"❌ G3 노션 접속 실패 ({code}): {hint}"]
    today = now.date()
    out = [f"🧭 G3 {day}: 후보 {len(cands)}건 · {week_balance(chain, today)}"]
    if not cands:
        return out + ["   후보가 아직 없음 (G2가 돌고 나면 다시)"]
    if done := [c.chain_no for c in cands if c.chain_no]:
        return out + [f"   이미 넘김: {', '.join(done)} → 건너뜀"]
    picks = choose(cands)
    if not picks:
        return out + ["   ⚠️ 매칭 질문(GQ)이 있는 후보가 없어 체인 행을 만들지 않음 → 질문 은행 확인"]
    numbers = [_plain(r.get("properties", {}).get("글 번호", {})) for r in chain]
    logs = [_plain(r.get("properties", {}).get("작업 기록", {})) for r in chain]
    made_before = {c.page_id: [no for no, log in zip(numbers, logs) if c.page_id[:8] in log] for c in picks}
    again = [int(m.group(1)) for v in made_before.values() for no in v if (m := re.match(r"[NT]-(\d+)$", no))]
    n = again[0] if again else next_number(numbers)   # 한쪽만 만들고 멈췄으면 같은 번호로 이어서
    for c, prefix in zip(picks, channels(picks)):
        made = made_before[c.page_id]
        if made:   # 행은 만들었는데 후보에 번호를 못 적은 경우(중간 실패) → 번호만 적는다
            out.append(f"   {c.rank}등 {c.title[:30]} → 이미 {', '.join(made)} 있음, 후보에 번호만 기록")
        else:
            row = row_for(c, prefix, n, today, db)
            made = [f"{prefix}-{n:03d}"]
            rev = row["properties"]["리뷰어"]["rich_text"][0]["text"]["content"]
            out.append(f"   {c.rank}등 {c.title[:30]} ({c.total or '상록'}) → {made[0]} {CHANNEL[prefix]} · 리뷰 {rev}"
                       + (" [dry-run]" if dry_run else ""))
            if not dry_run:
                _http.request_json("POST", f"{API}/pages", row, headers=h)
                time.sleep(pause)   # 노션 API 초당 3회 제한
        if not dry_run:
            _mark(c.page_id, ", ".join(made), h)
    return out


def _mark(page_id: str, numbers: str, h: dict) -> None:
    _http.request_json("PATCH", f"{API}/pages/{page_id}",
                       {"properties": {"선택": {"checkbox": True}, "체인 글 번호": {"rich_text": _text(numbers)}}}, headers=h)
