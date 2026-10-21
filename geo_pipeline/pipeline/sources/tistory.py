"""티스토리 상위 글 소스 2종.

허브 기준 '구글 검색 상위의 tistory.com 글'. 구글 검색 결과 화면을 긁는 것은
약관상 금지이므로 두 가지 합법 경로만 둔다.

- tistory_cse    : Google Programmable Search(Custom Search JSON API)
                   GOOGLE_CSE_KEY / GOOGLE_CSE_CX 필요. q에 site:tistory.com
- tistory_manual : 사람이 구글에서 본 상위 글 링크를 CSV로 붙여 넣는 방식
                   (GR_TISTORY_URLS_CSV · 열: group,keyword,rank,url[,title])
"""

from __future__ import annotations

import csv
from pathlib import Path

from .. import _http
from ..keywords import Query
from ..models import PostRef
from .base import BaseSource

CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


class TistoryCseSource(BaseSource):
    key = "tistory_cse"
    name = "티스토리(구글 CSE)"
    channel = "tistory"

    def search(self, query: Query) -> list[PostRef]:
        params = {
            "key": self.config.google_cse_key,
            "cx": self.config.google_cse_cx,
            "q": f"{query.query} site:tistory.com",
            "num": min(10, self.config.top_n),
            "gl": "kr",
            "hl": "ko",
        }
        data = _http.get_json(CSE_ENDPOINT, params=params, headers={"User-Agent": self.config.user_agent})
        _http.polite_sleep(self.config.request_delay_sec)
        return parse_cse_items(data.get("items") or [], query, self.key)


def parse_cse_items(items: list[dict], query: Query, source_key: str = "tistory_cse") -> list[PostRef]:
    out: list[PostRef] = []
    for item in items:
        link = item.get("link", "")
        if "tistory.com" not in link:
            continue
        metas = (item.get("pagemap") or {}).get("metatags") or [{}]
        published = (metas[0].get("article:published_time") or "")[:10]
        out.append(
            PostRef(
                channel="tistory",
                group=query.group,
                keyword=query.keyword,
                query=query.query,
                rank=len(out) + 1,
                title=(item.get("title") or "").strip(),
                url=link,
                published=published,
                source=source_key,
            )
        )
    return out


class TistoryManualSource(BaseSource):
    key = "tistory_manual"
    name = "티스토리(사람 입력 CSV)"
    channel = "tistory"

    def __init__(self, config) -> None:
        super().__init__(config)
        self._rows = _read_csv(Path(config.tistory_urls_csv or ""))

    def search(self, query: Query) -> list[PostRef]:
        if query.modifier:  # CSV는 1차 검색어 기준으로만 받는다
            return []
        rows = sorted(
            (r for r in self._rows if r.get("keyword", "").strip() == query.keyword),
            key=lambda r: int(r.get("rank") or 0),
        )
        return [
            PostRef(
                channel="tistory",
                group=(r.get("group") or query.group).strip(),
                keyword=query.keyword,
                query=query.query,
                rank=int(r.get("rank") or i + 1),
                title=(r.get("title") or "").strip(),
                url=r["url"].strip(),
                source=self.key,
            )
            for i, r in enumerate(rows)
            if r.get("url")
        ]


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))
