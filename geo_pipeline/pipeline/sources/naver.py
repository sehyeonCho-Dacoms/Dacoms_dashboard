"""네이버 검색 API(블로그) 어댑터 — 공식 API 두 창구.

- hub (기본)  : 네이버 클라우드 NAVER API HUB. 콘솔 > NAVER API HUB > Application > 인증 정보
               헤더 X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY
- legacy      : 네이버 개발자센터 (2026-07-31 신규 발급 종료, 2027-06-30 종료 예정으로 알려짐)
               헤더 X-Naver-Client-Id / X-Naver-Client-Secret
- 두 창구 모두 키는 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 에 넣는다 (NAVER_API_MODE로 고름)
- 파라미터·응답은 같다: items[] 에 title(<b> 강조 포함)·link·postdate(YYYYMMDD)
- HUB 주소는 첫 실행에서 확인 필요. 다르면 NAVER_BLOG_ENDPOINT 로 덮어쓴다.

블로그 검색 결과에는 네이버 밖 블로그도 섞이므로 blog.naver.com 글만 남긴다.
허브 기준 '검색어의 블로그 탭 상위'는 정확도순(sort=sim)에 해당한다.
"""

from __future__ import annotations

import html
import re
import urllib.parse

from .. import _http
from ..keywords import Query
from ..models import PostRef
from .base import BaseSource

ENDPOINTS = {
    "hub": "https://naverapihub.apigw.ntruss.com/search/v1/blog",
    "legacy": "https://openapi.naver.com/v1/search/blog.json",
}
AUTH_HEADERS = {
    "hub": ("X-NCP-APIGW-API-KEY-ID", "X-NCP-APIGW-API-KEY"),
    "legacy": ("X-Naver-Client-Id", "X-Naver-Client-Secret"),
}
_TAG = re.compile(r"<[^>]+>")


class NaverBlogSource(BaseSource):
    key = "naver"
    name = "네이버 블로그"
    channel = "naver"

    def search(self, query: Query) -> list[PostRef]:
        params = {
            "query": query.query,
            "display": min(100, self.config.top_n * 3),  # 네이버 밖 글을 걸러낼 여유분
            "start": 1,
            "sort": "sim",
        }
        data = _http.get_json(self.endpoint(), params=params, headers=self.headers())
        _http.polite_sleep(self.config.request_delay_sec)
        return parse_items(data.get("items") or [], query, self.key)

    def endpoint(self) -> str:
        return self.config.naver_blog_endpoint or ENDPOINTS[self.config.naver_api_mode]

    def headers(self) -> dict:
        id_header, secret_header = AUTH_HEADERS[self.config.naver_api_mode]
        return {
            id_header: self.config.naver_client_id or "",
            secret_header: self.config.naver_client_secret or "",
            "User-Agent": self.config.user_agent,
        }

    def page_url(self, ref: PostRef) -> str:
        return to_mobile_url(ref.url)


def parse_items(items: list[dict], query: Query, source_key: str = "naver") -> list[PostRef]:
    out: list[PostRef] = []
    for item in items:
        link = item.get("link", "")
        if urllib.parse.urlsplit(link).netloc not in ("blog.naver.com", "m.blog.naver.com"):
            continue
        out.append(
            PostRef(
                channel="naver",
                group=query.group,
                keyword=query.keyword,
                query=query.query,
                rank=len(out) + 1,
                title=clean_title(item.get("title", "")),
                url=link,
                published=_date(item.get("postdate", "")),
                source=source_key,
            )
        )
    return out


def clean_title(raw: str) -> str:
    return html.unescape(_TAG.sub("", raw)).strip()


def to_mobile_url(url: str) -> str:
    """blog.naver.com/{id}/{logNo} → m.blog.naver.com/{id}/{logNo}.

    PC 주소는 본문을 iframe으로 감싸 구조를 읽을 수 없어 모바일 주소를 연다.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.netloc == "blog.naver.com":
        qs = urllib.parse.parse_qs(parts.query)
        if "blogId" in qs and "logNo" in qs:  # PostView.naver?blogId=..&logNo=..
            return f"https://m.blog.naver.com/{qs['blogId'][0]}/{qs['logNo'][0]}"
        return urllib.parse.urlunsplit(("https", "m.blog.naver.com", parts.path, "", ""))
    return url


def _date(yyyymmdd: str) -> str:
    s = (yyyymmdd or "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s.isdigit() else ""
