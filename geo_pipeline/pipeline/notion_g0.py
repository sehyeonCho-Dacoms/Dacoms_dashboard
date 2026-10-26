"""G0 이슈 트래커 → 노션 'G0 이슈 트래커 (매일 의료 기사)' DB (NOTION_TOKEN 이 있을 때만).

거름망을 통과한 기사만 한 건 = 한 행으로 올린다. 기사 본문·API 요약은 넣지 않는다(RULE-11).
흥미도 점수·글 후보는 사람이 채운다. 같은 기사 ID 가 이미 있으면 건너뛴다(수집 창 26시간이
하루보다 길어 전날 기사가 겹친다).

DB 페이지 ⋯ → 연결 → 'GEO 체인' 통합(NOTION_TOKEN 의 통합)을 추가해야 쓸 수 있다.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

from . import _http
from .models import SCREEN_PASS, Article
from .notion import VERSION, _text

# AI 허브 > AX 스터디·실습 > 블로그 GEO 체인 > G0 이슈 트래커 (매일 의료 기사)
DEFAULT_G0_DB = "8ce054d4cba445a8be281754fbedb916"
API = "https://api.notion.com/v1"


def row(a: Article, day: str, db: str) -> dict:
    props: dict = {
        "제목": {"title": _text(a.title)},
        "수집일": {"date": {"start": day}},
        "매체": {"rich_text": _text(a.press)},
        "원문": {"url": a.url or None},
        "표시": {"multi_select": [{"name": f} for f in a.flags if f in ("논쟁", "법률")]},
        "검색어": {"rich_text": _text(a.query[:200])},
        "기사 ID": {"rich_text": _text(a.id)},
    }
    if a.naver_url:
        props["네이버 뉴스"] = {"url": a.naver_url}
    if a.published:
        props["발행 시각"] = {"date": {"start": a.published.isoformat(timespec="minutes")}}
    return {"parent": {"database_id": db}, "properties": props}


def existing_ids(db: str, headers: dict, since: str) -> set[str]:
    ids: set[str] = set()
    body: dict = {"page_size": 100, "filter": {"property": "수집일", "date": {"on_or_after": since}}}
    while True:
        res = _http.request_json("POST", f"{API}/databases/{db}/query", body, headers=headers)
        for r in res.get("results", []):
            rt = r.get("properties", {}).get("기사 ID", {}).get("rich_text", [])
            ids.add("".join(t.get("plain_text", "") for t in rt))
        if not res.get("has_more"):
            return ids
        body["start_cursor"] = res["next_cursor"]


def push(articles: list[Article], now: datetime, pause: float = 0.35) -> str:
    """통과 기사를 노션에 올리고 결과 한 줄을 돌려준다."""
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return "   노션: NOTION_TOKEN 이 없어 건너뜀"
    h = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}
    db = os.getenv("NOTION_G0_DB", DEFAULT_G0_DB)
    day = now.strftime("%Y-%m-%d")
    passed = [a for a in articles if a.screen == SCREEN_PASS]
    try:
        seen = existing_ids(db, h, (now - timedelta(days=3)).strftime("%Y-%m-%d"))
    except Exception as exc:
        code = getattr(exc, "code", "")
        hint = {404: "DB에 통합이 연결되지 않음 (DB 페이지 ⋯ → 연결 → 통합 추가)", 401: "토큰 오류"}.get(code, str(exc))
        return f"❌ 노션 G0 DB 접속 실패 ({code}): {hint}"
    new = [a for a in passed if a.id not in seen]
    for a in new:
        _http.request_json("POST", f"{API}/pages", row(a, day, db), headers=h)
        time.sleep(pause)   # 노션 API 초당 3회 제한
    return f"   노션: 통과 {len(passed)}건 중 새 기사 {len(new)}건 추가 (이미 있음 {len(passed) - len(new)}건)"
