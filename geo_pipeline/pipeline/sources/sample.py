"""오프라인 sample 소스 — 자격증명·네트워크 없이 노드 전체를 돌려 본다.

sample_data/search_results.json 의 가상 검색 결과와 sample_data/html/ 의
가상 글 HTML(네이버 모바일·티스토리 구조를 흉내 낸 것)을 쓴다. 실제 글이 아니다.
"""

from __future__ import annotations

import json

from ..keywords import Query
from ..models import PostRef
from .base import BaseSource


class SampleSource(BaseSource):
    key = "sample"
    name = "샘플(오프라인)"
    channel = ""

    def __init__(self, config) -> None:
        super().__init__(config)
        path = config.sample_dir / "search_results.json"
        self._rows: list[dict] = json.loads(path.read_text(encoding="utf-8"))
        self._html_by_url = {r["url"]: r["html"] for r in self._rows}

    def search(self, query: Query) -> list[PostRef]:
        if query.modifier:
            return []
        return [
            PostRef(
                channel=r["channel"],
                group=query.group,
                keyword=query.keyword,
                query=query.query,
                rank=r["rank"],
                title=r["title"],
                url=r["url"],
                published=r.get("published", ""),
                source=self.key,
            )
            for r in self._rows
            if r["keyword"] == query.keyword
        ]

    def load_page(self, ref: PostRef) -> str:
        return (self.config.sample_dir / "html" / self._html_by_url[ref.url]).read_text(encoding="utf-8")
