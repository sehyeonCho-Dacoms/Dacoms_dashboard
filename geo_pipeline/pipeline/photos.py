"""글 주제에 맞는 CC0 사진을 알아서 찾아 노션 원고 행에 붙인다 (사람이 검색어를 넣지 않음).

1. 제목·대상 질문의 한국어 핵심어 → 영어 검색어 (TOPIC_QUERIES, 순서가 우선순위)
2. Wikimedia Commons 에서 CC0·퍼블릭 도메인 사진만 후보 3장 (images.find_photo)
3. 노션 '블로그 GEO 체인' DB에서 아직 게시 전이고 사진이 없는 행에
   '📷 사진 후보 (CC0)' 섹션을 붙인다: 1순위 사진 미리보기 + 출처 캡션 + 다른 후보 링크 +
   원고 머리말에 붙여 넣을 photo_url 등.

작업 환경 IP가 Wikimedia 검색 API에서 막히는(429) 문제가 있어 GitHub Actions 에서 매일 돌린다.
검색어 표가 글 주제를 못 잡으면 TOPIC_QUERIES 에 한 줄 추가한다.
"""

from __future__ import annotations

import os
import time

from . import _http, images
from .notion import DEFAULT_DB, VERSION, _text

MARKER = "📷 사진 후보 (CC0)"
ACTIVE = {"원고작성", "검수통과", "사람확인"}   # 게시 전 단계
FALLBACK = "doctor stethoscope"

# (한국어 핵심어들, 영어 검색어) — 위에 있을수록 먼저 쓴다
TOPIC_QUERIES: list[tuple[tuple[str, ...], str]] = [
    (("근로계약", "계약서", "서명"), "signing contract document"),
    (("면접",), "job interview"),
    (("세금", "원천징수", "연말정산", "네트", "그로스", "세후", "세전"), "tax calculator"),
    (("퇴직금",), "piggy bank savings"),
    (("연봉", "급여", "수수료", "인센티브", "당직비"), "calculator money"),
    (("헤드헌팅", "헤드헌터", "매칭"), "business handshake"),
    (("당직",), "hospital corridor night"),
    (("지방", "지역의사"), "rural hospital"),
    (("간호사",), "nurse hospital"),
    (("원무과", "행정직", "인사 담당"), "hospital reception desk"),
    (("이직", "구인", "구직", "채용", "공고"), "job search laptop"),
    (("전공의", "전문의", "공보의", "봉직의", "페이닥터"), "doctor stethoscope"),
    (("병원", "의원"), "hospital building"),
]


def queries_for(*texts: str, n: int = 2) -> list[str]:
    """제목·질문에서 검색어를 n개 고르고 마지막에 기본 검색어를 붙인다."""
    joined = " ".join(texts)
    out: list[str] = []
    for words, q in TOPIC_QUERIES:
        if q not in out and any(w in joined for w in words):
            out.append(q)
        if len(out) >= n:
            break
    if FALLBACK not in out:
        out.append(FALLBACK)
    return out


def candidates(queries: list[str], want: int = 3, pause: float = 1.0) -> list[dict]:
    """검색어 순서대로 후보를 모은다 (같은 파일 중복 제외)."""
    found: list[dict] = []
    for q in queries:
        for ph in images.find_photo(q, limit=want) or []:
            if all(ph["page"] != f["page"] for f in found):
                found.append({**ph, "query": q})
        if len(found) >= want:
            break
        _http.polite_sleep(pause)
    return found[:want]


def caption(ph: dict) -> str:
    return f"사진: {ph['artist']} / Wikimedia Commons ({ph['license']}) {ph['page']}"


def blocks_for(found: list[dict]) -> list[dict]:
    best, rest = found[0], found[1:]
    front = "\n".join(f"photo_{k}: {best[k]}" for k in ("url", "page", "license", "artist"))
    out: list[dict] = [
        {"object": "block", "type": "heading_2", "heading_2": {"rich_text": _text(MARKER)}},
        {"object": "block", "type": "image",
         "image": {"type": "external", "external": {"url": best["url"]}, "caption": _text(caption(best))}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _text(
            f"1순위 · 검색어 '{best['query']}'. 4번째 이미지(첫 소제목 아래)로 쓰고 캡션을 그대로 붙이세요. "
            "원고 머리말에 아래 4줄을 넣으면 build --images 가 이 사진으로 4_photo.jpg 를 만듭니다.")}},
        {"object": "block", "type": "code", "code": {"language": "yaml", "rich_text": _text(front)}},
    ]
    for i, ph in enumerate(rest, 2):
        out.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [
            {"type": "text", "text": {"content": f"{i}순위: {ph['title']} — {ph['license']} · {ph['artist']} ",
                                      "link": None}},
            {"type": "text", "text": {"content": "보기", "link": {"url": ph["page"]}}},
        ]}})
    return out


def has_marker(blocks: list[dict]) -> bool:
    for b in blocks:
        rt = b.get(b.get("type", ""), {}).get("rich_text", [])
        if MARKER in "".join(t.get("plain_text", "") or t.get("text", {}).get("content", "") for t in rt):
            return True
    return False


def _plain(prop: dict) -> str:
    kind = prop.get("type", "")
    val = prop.get(kind)
    if kind in ("title", "rich_text"):
        return "".join(t.get("plain_text", "") for t in val or [])
    if kind in ("select", "status"):
        return (val or {}).get("name", "")
    if kind == "url":
        return val or ""
    return ""


def sync(dry_run: bool = False, pause: float = 1.0) -> list[str]:
    """노션 원고 행마다 사진 후보를 붙인다. 처리 결과 줄 목록을 돌려준다."""
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return ["❌ NOTION_TOKEN 이 없습니다"]
    h = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}
    db = os.getenv("NOTION_GEO_DB", DEFAULT_DB)
    rows = _http.request_json("POST", f"https://api.notion.com/v1/databases/{db}/query",
                              {"page_size": 100}, headers=h).get("results", [])
    log: list[str] = []
    for row in rows:
        p = row.get("properties", {})
        no, title = _plain(p.get("글 번호", {})), _plain(p.get("제목", {}))
        if _plain(p.get("상태", {})) not in ACTIVE or _plain(p.get("게시 URL", {})):
            continue
        kids = _http.request_json("GET", f"https://api.notion.com/v1/blocks/{row['id']}/children?page_size=100",
                                  headers=h).get("results", [])
        if has_marker(kids):
            log.append(f"- {no}: 이미 사진 후보 있음 → 건너뜀")
            continue
        qs = queries_for(title, _plain(p.get("대상 질문", {})))
        found = candidates(qs, pause=pause)
        if not found:
            log.append(f"- {no}: 후보 없음 (검색어 {', '.join(qs)}) → TOPIC_QUERIES 보강 필요")
            continue
        if not dry_run:
            _http.request_json("PATCH", f"https://api.notion.com/v1/blocks/{row['id']}/children",
                               {"children": blocks_for(found)}, headers=h)   # 페이지 끝에 붙음
        log.append(f"- {no} {title}: {found[0]['title']} ({found[0]['license']}) 외 {len(found) - 1}장"
                   f" · 검색어 {', '.join(qs)}" + (" [미리보기]" if dry_run else ""))
        time.sleep(pause)
    return log or ["- 사진을 붙일 원고 행이 없습니다 (게시 전 행 모두 처리됨)"]
