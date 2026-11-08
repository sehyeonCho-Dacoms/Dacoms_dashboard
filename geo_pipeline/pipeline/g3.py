"""G3 선택 → 체인 DB 글 행 (DR-GEO-02, 10/27 통합 인수인계 2장 · 준칙 v2 11/8).

G2가 그날 'G2 오늘의 후보' DB에 후보를 올리면, **그날 트랙의 1등을 자동 선택**해 '블로그 GEO 체인'
DB에 글 행을 만들고 상태를 '근거수집'으로 둔다. 이 행이 웅서(G4~G11)에게 넘기는 유일한 연결 고리다.

준칙 v2 (11/8 세현 결정, 노션 '블로그 GEO 체인 준칙 v2 (정본, 11/8)'):
- 평일만 발행, 주 10편. 월·수·금 = 의료 뉴스 트랙 / 화·목 = 채용·의사 일 트랙. 주말에는 행을 만들지 않는다.
- 주제 1개 = **N 행 1개**. 티스토리판도 같은 행에서 관리한다(게시 URL은 '티스토리 게시 URL' 칸).
  T 행은 더 만들지 않는다(11/5 이후 T 행에 발행 기록이 안 들어가던 문제, 웅서 작성 기준 11/8).
  두 채널 글은 같은 근거로 따로 쓰고 문장 유사도 80% 미만(D-037).
- 그날 트랙 후보가 없으면 의료 뉴스 날은 채용·의사 일 후보(상록 포함)로, 채용 날은 의료 뉴스 후보로 대신한다.
- 자동 실행 전에 사람이 '선택'을 체크해 두었으면 트랙과 상관없이 그 후보를 쓴다(덮어쓰기).
- 그날 후보 중 하나라도 '체인 글 번호'가 있으면 그날은 끝난 것으로 보고 건너뛴다. 지난 날짜는 손대지 않는다.

- 2장 필수 칸을 모두 채운다: 글 번호 · 제목(가제목) · 채널 · 타깃 · 대상 질문 · 질문 의도 · 트랙 ·
  원천 기사(뉴스만) · 흥미도 점수 · 담당(웅서) · 리뷰어(로테이션) · 작업 기록(고른 이유 + 원고 설계) · 상태.
- 채용·의사 일 후보는 매칭 질문(GQ)이 있어야 고른다(14일 중복 규칙). 의료 뉴스 후보는 GQ가 없어도 되고,
  대상 질문은 '뉴스 · …'로 적는다(G1이 '의료 뉴스' 묶음 대표 질문으로 추가).
- 고른 후보는 '선택' 체크 + '체인 글 번호'를 적는다.
- 행을 만든 뒤에는 2장 칸만 고친다(3장 칸은 웅서). 기사 본문·요약은 넣지 않는다(RULE-11).

11/5 세현 결정 (세계관 결정 목록):
- D-026·D-030: 후보 0건(16시 이후)·고를 후보가 없는 날은 ❌로 끝내 워크플로를 실패시키고 ⏸ 알림을 남긴다.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import _http, notify
from .g2 import BY_ID
from .models import TRACK_JOB, TRACK_NEWS
from .notion import DEFAULT_DB, VERSION, _text
from .notion_g0 import DEFAULT_G2_DB

API = "https://api.notion.com/v1"
STAGE = "근거수집"
OWNER = "웅서"
LATE_HOUR = 16   # KST. 이 시각 뒤에도 후보가 0건이면 실패(❌)로 본다 — G0는 실제 10~12시, 안전망은 실제 13~21시 (D-055)
PREFIX = "N"     # v2: 주제 1개 = N 행 1개 (티스토리판 포함)
CHANNEL_BOTH = "네이버 블로그"   # 채널 칸 선택지는 그대로 두고(웅서 blog.py가 읽음), 티스토리는 같은 행 URL 칸에
# 체인 DB 타깃은 의사/반의사 두 칸뿐. 병원(원장·인사 담당)은 반의사 형식, 공통은 의사 형식으로 쓴다.
TARGET = {"의사": "의사", "반의사": "반의사", "병원": "반의사", "공통": "의사"}
# 요일 → 트랙 (월0 … 금4). 주 10편 = 의료 뉴스 3주제(6편) + 채용·의사 일 2주제(4편)
TRACK_BY_DAY = {0: TRACK_NEWS, 1: TRACK_JOB, 2: TRACK_NEWS, 3: TRACK_JOB, 4: TRACK_NEWS}
WEEK_GOAL = {TRACK_NEWS: 3, TRACK_JOB: 2}
OPEN_DAY = date(2026, 11, 9)   # 닥터온 대외 오픈 — 이날부터 내부 링크 규칙이 바뀐다

# 로테이션 (부모 페이지 '로테이션' 표). 1주차 = 10/19 주. 통합 후 블로그 담당은 웅서로 고정이라
# 리뷰어가 웅서가 되는 주에는 그 주 블로그 담당(원래 글 쓸 사람)이 리뷰를 맡는다.
WEEK1 = date(2026, 10, 19)
ROTATION = [("세현", "웅서"), ("모세", "세현"), ("웅서", "모세")]   # (블로그, 리뷰어)

# 원고 설계: 준칙 v2 4장 '원고 형식' 표 + 웅서 채널별 작성 기준(11/8). G-R 월간 결과로 표가 바뀌면 여기도 고친다.
FORMAT = {
    ("의사", "N"): "소제목 5~8(절반 질문형) · 표 1(연봉·조건) · FAQ 2~3 · 현장 사례 익명 · 2,500~4,500자",
    ("의사", "T"): "h2·h3 6~10 · 비교표 1 이상 · FAQ 3 · 출처 목록 · 2,500~3,800자",
    ("반의사", "N"): "소제목 5~8 · 실무 팁·체크리스트 · FAQ 2 · 2,200~3,500자",
    ("반의사", "T"): "h2·h3 6~10 · 절차표 1 · 체크리스트 · FAQ 2 · 2,000~3,200자",
    ("뉴스", "N"): "소제목 5~6 · '무엇이 발표됐나 → 누구에게 무엇이 달라지나 → 언제부터' · FAQ 2 · 2,200~3,500자",
    ("뉴스", "T"): "h2·h3 6~8 · 발표 내용 요약표 1 · FAQ 2~3 · 원문 링크 · 2,000~3,200자",
}
# 원고 규칙 v2 핵심 (G5 작성 · G6 기계 점검 기준). 전문은 노션 정본
RULES_V2 = ("첫 줄=질문의 답(사진·자료 출처로 시작 금지, '닥터온 팀이 보기에' 금지) · 답 다음 범퍼 1문단 · "
            "티스토리 첫 문단 200자·조문 2개 이내 · 최근 12개월 공식 자료 1건+·공식 수치 5개+(법조문만 금지) · "
            "출처 괄호 문단당 1회(나머지 글 끝) · '닥터온 판단' 글당 2회 이내 · 현장 요소 1개 · "
            "네이버 대표 이미지는 자체 제작 카드 · 네이버 이모지 📌✅💡 2~5개·문장 단위 줄바꿈 · "
            "티스토리 제목 질문형/숫자형/정리형 순환 · 티스토리 끝 '작성: 닥터온 팀·작성일·확인일'")


def avoid_text(today: date) -> str:
    link = ("닥터온 내부 링크 금지(11/9 전)" if today < OPEN_DAY else
            "닥터온 내부 링크: 채용 글 1~2개(소개·가입 1 + 관련 글 1), 의료 뉴스 글 끝 1개")
    return f"기사 문장·순서 따라 쓰기 금지(RULE-11) · {link} · 닥터온 수치는 허브 확정값만"


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
    track: str = TRACK_JOB

    @property
    def gq(self) -> int | None:
        m = re.match(r"\s*GQ-(\d+)", self.question)
        return int(m.group(1)) if m else None

    @property
    def news(self) -> bool:
        return self.kind == "뉴스"

    @property
    def usable(self) -> bool:
        """고를 수 있는 후보: GQ가 질문 은행에 있거나, 원천 기사가 있는 의료 뉴스."""
        return self.gq in BY_ID or (self.track == TRACK_NEWS and self.news and bool(self.url))


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
        rank=int(float(g("순위") or 0)), checked=bool(p.get("선택", {}).get("checkbox")), chain_no=g("체인 글 번호"),
        track=g("트랙") or TRACK_JOB)   # v1 행(트랙 칸 없음)은 채용·의사 일


def day_track(day: date) -> str | None:
    """그날 트랙. 주말은 None (발행 없음)."""
    return TRACK_BY_DAY.get(day.weekday())


def choose(cands: list[Candidate], track: str = TRACK_JOB) -> list[Candidate]:
    """사람이 체크한 후보가 있으면 그것, 없으면 그날 트랙의 순위 1등. 그 트랙에 없으면 다른 트랙 1등."""
    ok = [c for c in cands if c.usable]
    if checked := [c for c in ok if c.checked]:
        return checked[:1]
    other = TRACK_JOB if track == TRACK_NEWS else TRACK_NEWS
    for t in (track, other):
        same = sorted((c for c in ok if c.track == t), key=lambda c: c.rank or 99)
        if same:
            return same[:1]
    return []


def intent(text: str) -> str:
    if "닥터온" in text:
        return "브랜드"
    if re.search(r"달라|차이|vs|비교", text):
        return "비교"
    if re.search(r"어떻게|방법|하는 법|준비|순서|확인할|체크", text):   # v2: '하는 법' 선택지 추가
        return "하는 법"
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


def work_log(c: Candidate, target: str, today: date, note: str, track: str) -> str:
    why = c.reason or ("상록 슬롯" if not c.news else "")
    key = "뉴스" if track == TRACK_NEWS else target
    ask = f"GQ-{c.gq} 질문" if c.gq else "이 뉴스로 독자가 물을 질문"
    must = f"첫 문단에서 {ask}에 바로 답" + (f" · {c.memo}" if c.memo else "")
    avoid = avoid_text(today)
    if c.marks:
        avoid += " · 표시 " + "·".join(c.marks) + " → 논쟁·법률 입장은 사람이 정함(DR-MKT-02)"
    if "의료" in c.marks or track == TRACK_NEWS:
        avoid += " · 의료 조언(진단·치료 권유·복용 안내) 금지, 치료·신약은 공식 발표·허가·급여 사실까지"
    if "근거 확인" in c.marks:
        avoid += " · 근거 확인: 30분 안에 최근 12개월 공식 자료 1건 못 찾으면 작업 기록에 '근거 부족 되돌림'"
    how = "사람 선택" if c.checked else f"자동 선택 {c.rank}등"
    head = f"{today:%m/%d} G3 {how} ({c.kind} · {track} · 후보 {c.day} {c.page_id[:8]})"
    parts = [head, f"고른 이유: {why}" if why else "",
             f"원고 설계 — 네이버: {FORMAT[(key, 'N')]} / 티스토리: {FORMAT[(key, 'T')]}",
             "티스토리판도 이 행에서 관리(게시 URL은 '티스토리 게시 URL' 칸) · 두 글은 같은 근거, 문장 유사도 80% 미만(D-037)",
             f"원고 규칙 v2: {RULES_V2}",
             f"꼭 다룰 점: {must}", f"피할 점: {avoid}", note]
    return "\n".join(x for x in parts if x)


def row_for(c: Candidate, number: int, today: date, db: str, track: str | None = None) -> dict | None:
    """후보 1건 → 체인 DB N 행 1개(티스토리판 포함). 고를 수 없는 후보면 None."""
    if not c.usable:
        return None
    track = track or c.track
    q = BY_ID.get(c.gq) if c.gq else None
    target = TARGET.get(c.target or (q.target if q else ""), "의사")
    rev, note = reviewer(today)
    if q:
        title, question = q.text, f"GQ-{q.gq} {q.text} ({q.priority} · {q.evergreen} · {q.ready})"
    else:   # 질문 은행 밖 의료 뉴스: 가제목은 웅서가 질문형으로 바꾼다(기사 제목은 게시 글에 쓰지 않음)
        title, question = f"(가제) {c.title}", f"뉴스 · {c.title} → G1 '의료 뉴스' 묶음 대표 질문 추가"
    props = {
        "글 번호": {"title": _text(f"{PREFIX}-{number:03d}")},
        "제목": {"rich_text": _text(title)},
        "채널": {"select": {"name": CHANNEL_BOTH}},
        "타깃": {"select": {"name": target}},
        "대상 질문": {"rich_text": _text(question)},
        "질문 의도": {"select": {"name": intent(q.text) if q else "정보"}},
        "트랙": {"select": {"name": track}},
        "흥미도 점수": {"rich_text": _text(score_text(c))},
        "담당": {"rich_text": _text(OWNER)},
        "리뷰어": {"rich_text": _text(rev)},
        "작업 기록": {"rich_text": _text(work_log(c, target, today, note, track))},
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
    """이번 주(월~) 체인 N 행의 트랙·타깃 수 — 주간 목표(의료 뉴스 3주제 + 채용·의사 일 2주제) 확인용."""
    monday = (today - timedelta(days=today.weekday())).isoformat()
    p = lambda r, k: _plain(r.get("properties", {}).get(k, {}))
    rows = [r for r in chain if r.get("created_time", "") >= monday and p(r, "글 번호").startswith("N-")]
    news = sum(1 for r in rows if p(r, "트랙") == TRACK_NEWS)
    job = sum(1 for r in rows if p(r, "트랙") == TRACK_JOB)
    doc = sum(1 for r in rows if p(r, "트랙") == TRACK_JOB and p(r, "타깃") == "의사")
    return (f"이번 주 주제 {len(rows)}개 · 의료 뉴스 {news}/{WEEK_GOAL[TRACK_NEWS]} · 채용·의사 일 {job}/{WEEK_GOAL[TRACK_JOB]}"
            f"(그중 의사 {doc}) · 목표 주 10편")


def run(now: datetime, dry_run: bool = False, pause: float = 0.35, day: str | None = None) -> list[str]:
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return ["   G3: NOTION_TOKEN 이 없어 건너뜀"]
    day = day or now.strftime("%Y-%m-%d")
    track = day_track(date.fromisoformat(day))
    if track is None:
        return [f"🧭 G3 {day}: 주말 — 준칙 v2는 평일만 발행해 체인 행을 만들지 않음"]
    h = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}
    db = os.getenv("NOTION_GEO_DB", DEFAULT_DB)
    g2_db = os.getenv("NOTION_G2_DB", DEFAULT_G2_DB)
    try:
        cands = day_candidates(g2_db, day, h)
        chain = _query(db, {}, h)
    except Exception as exc:
        code = getattr(exc, "code", "")
        hint = {404: "DB에 통합이 연결되지 않음", 401: "토큰 오류",
                400: "후보 DB에 '체인 글 번호'·'트랙' 칸이 있는지 확인"}.get(code, str(exc))
        return [f"❌ G3 노션 접속 실패 ({code}): {hint}"]
    today = now.date()
    out = [f"🧭 G3 {day} ({track} 날): 후보 {len(cands)}건 · {week_balance(chain, today)}"]
    if not cands:
        if now.hour >= LATE_HOUR:   # 16시가 넘었는데도 후보가 없으면 그날 체인이 멈춘 것 (10/30 사고)
            return out + [f"❌ G3: {day} 후보가 없어 체인 행을 만들지 못함",
                          notify.alert("G2→G3", "그날 후보 0건", "G0·G2 실행 기록 확인, 질문 은행 '바로 가능' 보충(D-036)")]
        return out + ["   후보가 아직 없음 (G2가 돌고 나면 다시)"]
    if done := [c.chain_no for c in cands if c.chain_no]:
        return out + [f"   이미 넘김: {', '.join(done)} → 건너뜀"]
    picks = choose(cands, track)
    if not picks:
        return out + ["❌ G3: 고를 수 있는 후보(GQ 있는 채용 후보 또는 원천 기사 있는 의료 뉴스)가 없어 체인 행을 만들지 못함",
                      notify.alert("G1→G3", "후보에 맞는 질문 없음", "질문 은행에 질문 추가 후 g2.py 스냅샷 갱신, 또는 후보 '선택'")]
    c = picks[0]
    used = c.track if c.checked else track if c.track == track else c.track
    if used != track:
        out.append(f"   {track} 후보가 없어 {used} 후보로 대신함")
    numbers = [_plain(r.get("properties", {}).get("글 번호", {})) for r in chain]
    logs = [_plain(r.get("properties", {}).get("작업 기록", {})) for r in chain]
    made = [no for no, log in zip(numbers, logs) if c.page_id[:8] in log and no.startswith(f"{PREFIX}-")]
    if made:   # 행은 만들었는데 후보에 번호를 못 적은 경우(중간 실패) → 번호만 적는다
        out.append(f"   {c.rank}등 {c.title[:30]} → 이미 {', '.join(made)} 있음, 후보에 번호만 기록")
    else:
        n = next_number(numbers)
        row = row_for(c, n, today, db, track=used)
        made = [f"{PREFIX}-{n:03d}"]
        rev = row["properties"]["리뷰어"]["rich_text"][0]["text"]["content"]
        out.append(f"   {c.rank}등 {c.title[:30]} ({c.total or '상록'}) → {made[0]} 네이버·티스토리 한 행 · {used}"
                   f" · 리뷰 {rev}" + (" [dry-run]" if dry_run else ""))
        if not dry_run:
            _http.request_json("POST", f"{API}/pages", row, headers=h)
            time.sleep(pause)   # 노션 API 초당 3회 제한
    if not dry_run:
        _mark(c.page_id, ", ".join(made), h)
    return out


def _mark(page_id: str, numbers: str, h: dict) -> None:
    _http.request_json("PATCH", f"{API}/pages/{page_id}",
                       {"properties": {"선택": {"checkbox": True}, "체인 글 번호": {"rich_text": _text(numbers)}}}, headers=h)
