"""노션 '블로그 GEO 체인' DB에 원고 행 만들기 (NOTION_TOKEN 이 있을 때만).

행 = 글 1건(체인 v1 컨베이어 벨트). 상태는 검수 결과에 따라 '검수통과' 또는 '사람확인'.
완성본 HTML 두 개와 검수 보고서는 페이지 본문(코드 블록)에 넣는다. 사람은 여기서
복사해 붙여 넣고 게시한 뒤 '게시 URL'과 상태 '게시완료'를 채운다(G7).

토큰: notion.so/my-integrations 에서 내부 통합을 만들고, DB 페이지 '연결'에 그 통합을 추가.
"""

from __future__ import annotations

import os

from . import _http
from .draft import Draft

API = "https://api.notion.com/v1/pages"
VERSION = "2022-06-28"
# 블로그 GEO 체인 DB (AI 허브 > AX 스터디·실습 > 블로그 GEO 체인)
DEFAULT_DB = "334368830af342eb918f9967ff8a6e6e"
_CHUNK = 1900   # 노션 rich_text 한 조각 최대 2000자


def _text(s: str) -> list[dict]:
    return [{"type": "text", "text": {"content": s[i:i + _CHUNK]}} for i in range(0, len(s), _CHUNK)][:100]


def _code(title: str, body: str, lang: str) -> list[dict]:
    return [
        {"object": "block", "type": "heading_2", "heading_2": {"rich_text": _text(title)}},
        {"object": "block", "type": "code", "code": {"language": lang, "rich_text": _text(body)}},
    ]


def build_page(d: Draft, tistory_html: str, naver_html: str, report: str, verdict: str, db: str) -> dict:
    channel = {"tistory": "티스토리", "naver": "네이버 블로그"}.get(d.channel)
    props: dict = {
        "글 번호": {"title": _text(d.meta.get("id", d.title[:20]))},
        "제목": {"rich_text": _text(d.title)},
        "상태": {"select": {"name": "사람확인" if verdict.startswith("불합격") else "검수통과"}},
        "검수 결과": {"rich_text": _text(f"{verdict} (G6 자동 검수)")},
        "대상 질문": {"rich_text": _text(d.meta.get("question", ""))},
    }
    if channel:
        props["채널"] = {"select": {"name": channel}}
    if d.meta.get("target") in ("의사", "반의사"):
        props["타깃"] = {"select": {"name": d.meta["target"]}}
    children = (_code("G6 자동 검수", report, "markdown")
                + _code("티스토리 붙여 넣기 (HTML 모드)", tistory_html, "html")
                + _code("네이버 붙여 넣기", naver_html, "html"))
    return {"parent": {"database_id": db}, "properties": props, "children": children}


def push(d: Draft, tistory_html: str, naver_html: str, report: str, verdict: str) -> str | None:
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return None
    page = build_page(d, tistory_html, naver_html, report, verdict, os.getenv("NOTION_GEO_DB", DEFAULT_DB))
    res = _http.post_json(API, page, headers={"Authorization": f"Bearer {token}", "Notion-Version": VERSION})
    return res.get("url")
