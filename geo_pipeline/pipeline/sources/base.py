"""검색 소스 공통 인터페이스.

각 소스는 `search(query)`로 검색어 하나의 상위 글 목록(PostRef)을 돌려주고,
`load_page(ref)`로 글 HTML을 연다. 페이지 열기는 robots.txt 확인을 거친다.
개별 검색어 실패가 전체를 막지 않도록 `collect()`가 방어한다.
"""

from __future__ import annotations

from .. import _http
from ..config import Config
from ..keywords import Query
from ..models import PostRef


class RobotsBlocked(Exception):
    """robots.txt가 이 URL 수집을 허용하지 않음."""


class BaseSource:
    key: str = "base"
    name: str = "Base"
    channel: str = ""     # naver | tistory

    def __init__(self, config: Config) -> None:
        self.config = config

    def search(self, query: Query) -> list[PostRef]:  # pragma: no cover - 추상
        raise NotImplementedError

    def page_url(self, ref: PostRef) -> str:
        """구조 측정용으로 실제 열 URL (네이버는 모바일 주소로 바꾼다)."""
        return ref.url

    def load_page(self, ref: PostRef) -> str:
        url = self.page_url(ref)
        if not _http.allowed_by_robots(url, self.config.user_agent):
            raise RobotsBlocked(url)
        html = _http.get_text(url, headers={"User-Agent": self.config.user_agent})
        _http.polite_sleep(self.config.request_delay_sec)
        return html

    def collect(self, queries: list[Query]) -> list[PostRef]:
        out: list[PostRef] = []
        for q in queries:
            try:
                refs = self.search(q)
            except Exception as exc:
                print(f"  ⚠️  {self.name} '{q.query}' 검색 실패: {exc}")
                continue
            per_channel: dict[str, int] = {}
            for ref in refs:  # 채널별 상위 N개 (네이버 검색이 티스토리 글도 함께 줄 때)
                per_channel[ref.channel] = per_channel.get(ref.channel, 0) + 1
                if per_channel[ref.channel] <= self.config.top_n:
                    out.append(ref)
        return out
