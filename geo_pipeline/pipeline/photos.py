"""글 주제에 맞는 CC0 사진을 알아서 찾아 노션 원고 행에 붙인다 (사람이 검색어를 넣지 않음).

1. 제목·대상 질문의 한국어 핵심어 → 영어 검색어 (TOPIC_QUERIES, 순서가 우선순위)
2. Pexels 스톡 사진(PEXELS_API_KEY) 또는 Wikimedia Commons CC0 사진 후보 3장 (images.find_photo)
3. 노션 '블로그 GEO 체인' DB에서 아직 게시 전이고 사진이 없는 행에
   '📷 사진 후보 (CC0)' 섹션을 붙인다: 1순위 사진 미리보기 + 출처 캡션 + 다른 후보 링크 +
   원고 머리말에 붙여 넣을 photo_url 등.

작업 환경 IP가 Wikimedia 검색 API에서 막히는(429) 문제가 있어 GitHub Actions 에서 매일 돌린다.
검색어 표가 글 주제를 못 잡으면 TOPIC_QUERIES 에 한 줄 추가한다.
"""

from __future__ import annotations

import os
import re
import time

from . import _http, images
from .notion import DEFAULT_DB, VERSION, _text

MARKER = "📷 사진 후보"   # 예전 섹션 제목 "📷 사진 후보 (CC0)" 도 이 문자열로 찾는다
ACTIVE = {"원고작성", "검수통과", "사람확인"}   # 게시 전 단계
FALLBACK = ["doctor", "stethoscope", "hospital"]

# (한국어 핵심어들, 영어 검색어 후보). 주제어는 제목에서 먼저 나오는 것부터 쓰고,
# 일반어(GENERIC: 이직·의사·병원)는 주제어가 모자랄 때만 쓴다. 검색어는 짧을수록 CC0 후보가 많다.
TOPIC_QUERIES: list[tuple[tuple[str, ...], list[str]]] = [
    (("근로계약", "계약서", "서명"), ["contract signing", "signing document", "pen paper"]),
    (("면접",), ["job interview", "interview", "business meeting"]),
    (("네트", "그로스", "세금", "원천징수", "연말정산", "세후", "세전"), ["tax", "calculator", "payroll"]),
    (("퇴직금",), ["piggy bank", "savings", "coins"]),
    (("연봉", "급여", "수수료", "인센티브", "당직비"), ["salary", "calculator", "money"]),
    (("헤드헌팅", "헤드헌터", "매칭"), ["business handshake", "handshake", "recruitment"]),
    (("당직",), ["hospital corridor", "night shift", "hospital"]),
    (("지방", "지역의사"), ["rural hospital", "countryside", "hospital"]),
    (("간호사",), ["nurse", "hospital"]),
    (("원무과", "행정직", "인사 담당"), ["reception desk", "office", "paperwork"]),
]
GENERIC: list[tuple[tuple[str, ...], list[str]]] = [
    (("이직", "구인", "구직", "채용", "공고"), ["job search", "laptop office", "career"]),
    (("전공의", "전문의", "공보의", "봉직의", "페이닥터"), ["doctor", "physician"]),
    (("병원", "의원"), ["hospital", "clinic"]),
]


def queries_for(title: str, *more: str, n: int = 2) -> list[str]:
    """제목(+질문)에서 주제를 n개 고르고, 주제마다 검색어 후보를 이어 붙인 뒤 기본 검색어를 붙인다.

    주제어는 제목에서 먼저 나온 순서 → 질문에서 나온 순서, 그다음 일반어.
    """
    text = " ".join((title, *more))

    def first_pos(words: tuple[str, ...]) -> int:
        return min((text.find(w) for w in words if w in text), default=-1)

    hits = sorted(((pos, i, qs) for i, (words, qs) in enumerate(TOPIC_QUERIES) if (pos := first_pos(words)) >= 0),
                  key=lambda t: t[:2])
    hits += [(10**6, i, qs) for i, (words, qs) in enumerate(GENERIC) if first_pos(words) >= 0]
    out: list[str] = []
    for _, _, qs in hits[:n]:
        out += [q for q in qs if q not in out]
    out += [q for q in FALLBACK if q not in out]
    return out


def candidates(queries: list[str], want: int = 3, pause: float = 1.0, exclude: set[str] | None = None) -> list[dict]:
    """검색어 순서대로 후보를 모은다 (같은 파일·다른 글에서 쓴 사진 제외)."""
    found: list[dict] = []
    exclude = exclude or set()
    for q in queries:
        for ph in images.find_photo(q, limit=want + len(exclude)) or []:
            if ph["page"] not in exclude and all(ph["page"] != f["page"] for f in found):
                found.append({**ph, "query": q})
        if len(found) >= want:
            break
        _http.polite_sleep(pause)
    return found[:want]


def caption(ph: dict) -> str:
    return images.photo_caption(ph)


def blocks_for(found: list[dict]) -> list[dict]:
    best, rest = found[0], found[1:]
    front = "\n".join(f"photo_{k}: {best[k]}" for k in ("url", "page", "license", "artist"))
    out: list[dict] = [
        {"object": "block", "type": "heading_2", "heading_2": {"rich_text": _text(f"{MARKER} ({best.get('source', 'CC0')})")}},
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


def _block_text(b: dict) -> str:
    rt = b.get(b.get("type", ""), {}).get("rich_text", [])
    return "".join(t.get("plain_text", "") or t.get("text", {}).get("content", "") for t in rt)


def marker_index(blocks: list[dict]) -> int:
    """'📷 사진 후보' 제목 블록 위치, 없으면 -1."""
    return next((i for i, b in enumerate(blocks) if MARKER in _block_text(b)), -1)


def has_marker(blocks: list[dict]) -> bool:
    return marker_index(blocks) >= 0


def used_photo(blocks: list[dict]) -> str | None:
    """붙어 있는 사진 섹션의 1순위 photo_page."""
    i = marker_index(blocks)
    for b in blocks[i:] if i >= 0 else []:
        if m := re.search(r"photo_page:\s*(\S+)", _block_text(b)):
            return m.group(1)
    return None


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


def sync(dry_run: bool = False, pause: float = 1.0, replace: bool = False) -> list[str]:
    """노션 원고 행마다 사진 후보를 붙인다. replace=True 면 이미 붙은 사진 섹션을 지우고 다시 찾는다."""
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return ["❌ NOTION_TOKEN 이 없습니다"]
    h = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}
    api = "https://api.notion.com/v1"
    db = os.getenv("NOTION_GEO_DB", DEFAULT_DB)
    rows = _http.request_json("POST", f"{api}/databases/{db}/query", {"page_size": 100}, headers=h).get("results", [])

    # 1차: 게시 전 행과 그 본문을 모으고, 다른 글에 이미 쓰인 사진을 기록한다
    todo: list[tuple[dict, list[dict]]] = []
    used: set[str] = set()
    log: list[str] = []
    for row in rows:
        p = row.get("properties", {})
        if _plain(p.get("상태", {})) not in ACTIVE or _plain(p.get("게시 URL", {})):
            continue
        kids = _http.request_json("GET", f"{api}/blocks/{row['id']}/children?page_size=100", headers=h).get("results", [])
        if has_marker(kids) and not replace:
            if page := used_photo(kids):
                used.add(page)
            log.append(f"- {_plain(p.get('글 번호', {}))}: 이미 사진 후보 있음 → 건너뜀")
            continue
        todo.append((row, kids))

    # 2차: 글마다 다른 사진으로 후보를 찾아 붙인다
    for row, kids in todo:
        p = row["properties"]
        no, title = _plain(p.get("글 번호", {})), _plain(p.get("제목", {}))
        qs = queries_for(title, _plain(p.get("대상 질문", {})))
        found = candidates(qs, pause=pause, exclude=used)
        if not found:
            log.append(f"- {no}: 후보 없음 (검색어 {', '.join(qs)}) → TOPIC_QUERIES 보강 필요")
            continue
        used.add(found[0]["page"])
        if not dry_run:
            if (i := marker_index(kids)) >= 0:   # replace: 예전 사진 섹션(맨 끝)을 지운다
                for b in kids[i:]:
                    _http.request_json("DELETE", f"{api}/blocks/{b['id']}", headers=h)
            _http.request_json("PATCH", f"{api}/blocks/{row['id']}/children",
                               {"children": blocks_for(found)}, headers=h)   # 페이지 끝에 붙음
        log.append(f"- {no} {title} · 검색어 {', '.join(qs)}" + (" [미리보기]" if dry_run else ""))
        log += [f"  {i}. {ph['title']} ({ph['license']}) {ph['page']}" for i, ph in enumerate(found, 1)]
        time.sleep(pause)
    return log or ["- 사진을 붙일 원고 행이 없습니다 (게시 전 행 모두 처리됨)"]
