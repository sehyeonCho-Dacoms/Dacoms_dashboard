"""G0 이슈 트래커 → 노션 '블로그 GEO 체인' DB (NOTION_TOKEN 이 있을 때만).

거름망을 통과한 기사 1건 = 체인 DB 1행, 상태 '질문선택'(체인 첫 단계). 사람이 흥미도 점수를
매기고 글로 쓸 기사만 다음 단계로 넘긴다. 기사 본문·API 요약은 넣지 않는다(RULE-11).
같은 기사 ID(글 번호)가 최근 3일 안에 있으면 건너뛴다(수집 창 26시간이 하루와 겹침).
"""

from __future__ import annotations

import os
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
