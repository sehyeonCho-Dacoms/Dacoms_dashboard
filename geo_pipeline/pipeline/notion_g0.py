"""G0 이슈 트래커 → 노션 '블로그 GEO 체인' DB (NOTION_TOKEN 이 있을 때만).

거름망을 통과한 기사 1건 = 체인 DB 1행, 상태 '질문선택'(체인 첫 단계). 사람이 흥미도 점수를
매기고 글로 쓸 기사만 다음 단계로 넘긴다. 기사 본문·API 요약은 넣지 않는다(RULE-11).
같은 기사 ID(글 번호)가 최근 3일 안에 있으면 건너뛴다(수집 창 26시간이 하루와 겹침).
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta

from . import _http
from .models import SCREEN_PASS, Article
from .notion import DEFAULT_DB, VERSION, _text

API = "https://api.notion.com/v1"
STAGE = "질문선택"


def row(a: Article, day: str, db: str) -> dict:
    note = " · ".join(x for x in (
        f"G0 자동 수집 {day}", a.press, f"검색어 {a.query}" if a.query else "",
        f"표시 {', '.join(a.flags)}" if a.flags else "",
        f"발행 {a.published.strftime('%m/%d %H:%M')}" if a.published else "",
        f"네이버 {a.naver_url}" if a.naver_url else "") if x)
    return {"parent": {"database_id": db}, "properties": {
        "글 번호": {"title": _text(a.id)},
        "제목": {"rich_text": _text(a.title)},
        "원천 기사": {"url": a.url or None},
        "상태": {"select": {"name": STAGE}},
        "작업 기록": {"rich_text": _text(note)},
    }}


def existing_ids(db: str, headers: dict, since: str) -> set[str]:
    ids: set[str] = set()
    body: dict = {"page_size": 100, "filter": {"and": [
        {"property": "글 번호", "title": {"starts_with": "N-"}},
        {"timestamp": "created_time", "created_time": {"on_or_after": since}},
    ]}}
    while True:
        res = _http.request_json("POST", f"{API}/databases/{db}/query", body, headers=headers)
        for r in res.get("results", []):
            ids.add("".join(t.get("plain_text", "") for t in r.get("properties", {}).get("글 번호", {}).get("title", [])))
        if not res.get("has_more"):
            return ids
        body["start_cursor"] = res["next_cursor"]


def push(articles: list[Article], now: datetime, pause: float = 0.35) -> str:
    """통과 기사를 체인 DB에 '질문선택' 행으로 올리고 결과 한 줄을 돌려준다."""
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return "   노션: NOTION_TOKEN 이 없어 건너뜀"
    h = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}
    db = os.getenv("NOTION_GEO_DB", DEFAULT_DB)
    day = now.strftime("%Y-%m-%d")
    passed = [a for a in articles if a.screen == SCREEN_PASS]
    try:
        seen = existing_ids(db, h, (now - timedelta(days=3)).strftime("%Y-%m-%d"))
    except Exception as exc:
        code = getattr(exc, "code", "")
        hint = {404: "DB에 통합이 연결되지 않음", 401: "토큰 오류"}.get(code, str(exc))
        return f"❌ 노션 '블로그 GEO 체인' 접속 실패 ({code}): {hint}"
    new = [a for a in passed if a.id not in seen]
    for a in new:
        _http.request_json("POST", f"{API}/pages", row(a, day, db), headers=h)
        time.sleep(pause)   # 노션 API 초당 3회 제한
    return (f"   노션 '블로그 GEO 체인': 통과 {len(passed)}건 중 새 기사 {len(new)}건을 '{STAGE}'로 추가"
            f" (이미 있음 {len(passed) - len(new)}건)")


def chain_questions(now: datetime) -> tuple[set[int], dict[int, str]] | None:
    """체인 DB에서 (글을 쓴 질문 GQ 번호들, 최근 14일 안에 쓴 질문 → 글 번호)를 읽는다. 읽기만 한다.

    G2 상록 슬롯(글 없는 질문)과 거름망 ⑥(14일 안 같은 질문 글 → 업데이트 후보)에 쓴다.
    """
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return None
    h = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}
    db = os.getenv("NOTION_GEO_DB", DEFAULT_DB)
    written: set[int] = set()
    recent: dict[int, str] = {}
    since = (now - timedelta(days=14)).isoformat()
    body: dict = {"page_size": 100}
    while True:
        res = _http.request_json("POST", f"{API}/databases/{db}/query", body, headers=h)
        for r in res.get("results", []):
            p = r.get("properties", {})
            q = "".join(t.get("plain_text", "") for t in p.get("대상 질문", {}).get("rich_text", []))
            no = "".join(t.get("plain_text", "") for t in p.get("글 번호", {}).get("title", []))
            for m in re.findall(r"GQ-(\d+)", q):
                written.add(int(m))
                if r.get("created_time", "") >= since:
                    recent[int(m)] = no
        if not res.get("has_more"):
            return written, recent
        body["start_cursor"] = res["next_cursor"]


# --------------------------------------------------------------------------- #
# G2 → 노션 'G2 오늘의 후보' DB (체인 DB 앞 단계). 행 = 그날 후보 1건. G3 담당자가 '선택'을 체크한
# 1건만 체인 DB의 글 행이 된다. 같은 날짜 행이 이미 있으면 다시 올리지 않는다(수동 재실행 대비).
# --------------------------------------------------------------------------- #
DEFAULT_G2_DB = "5c99c33be0114c328d7d41c14bb74105"


def candidate_rows(top, slots, day: str, db: str) -> list[dict]:
    rows = []
    for i, s in enumerate(top, 1):
        a = s.article
        props = {
            "후보": {"title": _text(a.title)},
            "날짜": {"date": {"start": day}},
            "순위": {"number": i},
            "종류": {"select": {"name": "뉴스"}},
            "총점": {"number": s.total},
            "점수 내역": {"rich_text": _text(f"A{s.a} B{s.b} C{s.c} D{s.d} E{s.e} F{s.f}")},
            "타깃": {"select": {"name": s.target}},
            "채널": {"select": {"name": s.channel}},
            "매칭 질문": {"rich_text": _text(f"GQ-{s.gq.gq} {s.gq.text}" if s.gq else "없음 → 좋은 기사면 G1 새 질문 후보")},
            "원천 기사": {"url": a.url or None},
            "매체": {"rich_text": _text(a.press)},
            "표시": {"multi_select": [{"name": m} for m in s.marks if m in ("논쟁", "법률")]},
            "한 줄 이유": {"rich_text": _text(s.reason)},
            "기사 ID": {"rich_text": _text(a.id)},
        }
        rows.append({"parent": {"database_id": db}, "properties": props})
    for j, q in enumerate(slots, len(top) + 1):
        props = {
            "후보": {"title": _text(f"GQ-{q.gq} {q.text}")},
            "날짜": {"date": {"start": day}},
            "순위": {"number": j},
            "종류": {"select": {"name": "상록 슬롯"}},
            "타깃": {"select": {"name": q.target}},
            "채널": {"select": {"name": q.channel}},
            "매칭 질문": {"rich_text": _text(f"GQ-{q.gq} {q.text}")},
            "한 줄 이유": {"rich_text": _text(f"60점 이상 뉴스가 모자라 질문 은행 {q.priority}·글 없음·바로 가능에서 채움(준칙 3-4)")},
        }
        rows.append({"parent": {"database_id": db}, "properties": props})
    return rows


def push_candidates(top, slots, now: datetime) -> str:
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return "   노션 후보 DB: NOTION_TOKEN 이 없어 건너뜀"
    h = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}
    db = os.getenv("NOTION_G2_DB", DEFAULT_G2_DB)
    day = now.strftime("%Y-%m-%d")
    try:
        res = _http.request_json("POST", f"{API}/databases/{db}/query",
                                 {"page_size": 1, "filter": {"property": "날짜", "date": {"equals": day}}}, headers=h)
    except Exception as exc:
        code = getattr(exc, "code", "")
        hint = {404: "후보 DB에 통합이 연결되지 않음 (DB 페이지 ⋯ → 연결 → 통합 추가)", 401: "토큰 오류"}.get(code, str(exc))
        return f"❌ 노션 'G2 오늘의 후보' 접속 실패 ({code}): {hint}"
    if res.get("results"):
        return f"   노션 후보 DB: {day} 후보가 이미 있어 건너뜀"
    for row in candidate_rows(top, slots, day, db):
        _http.request_json("POST", f"{API}/pages", row, headers=h)
        time.sleep(0.35)
    return f"   노션 'G2 오늘의 후보': {day} 후보 {len(top)}건 + 상록 슬롯 {len(slots)}건 저장"
