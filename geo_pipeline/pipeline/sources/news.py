"""G0 이슈 트래커 뉴스 소스 3종.

- naver_news : 네이버 뉴스 검색 API (블로그 검색과 같은 키·창구, sort=date 최신순)
- rss        : 의료 전문지 RSS/Atom (G0_RSS_FEEDS, 쉼표구분). 매체 약관·robots 확인 후 추가
- sample     : 오프라인 가상 기사 (sample_data/news_sample.json, 실제 기사 아님)

10/16 합의대로 키워드로 미리 거르지 않는다. 검색어는 넓게 잡고, 거르는 일은
screen.py(거름망)와 G2 흥미도 점수가 맡는다.
"""

from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .. import _http
from ..config import Config
from ..models import Article
from .naver import AUTH_HEADERS, naver_headers

KST = timezone(timedelta(hours=9))

# 넓은 수집 검색어: 의사·병원 인력과 정책을 두루 덮는다
DEFAULT_QUERIES = [
    "의사", "전공의", "의대 정원", "병원 채용", "간호사", "의료 인력",
    "필수의료", "지역의료", "수가", "보건복지부 의료", "개원의", "공보의",
]

NEWS_ENDPOINTS = {
    "hub": "https://naverapihub.apigw.ntruss.com/search/v1/news",
    "legacy": "https://openapi.naver.com/v1/search/news.json",
}
assert NEWS_ENDPOINTS.keys() == AUTH_HEADERS.keys()

_TAG = re.compile(r"<[^>]+>")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub("", text or ""))).strip()


def parse_date(value: str) -> datetime | None:
    """RFC 822(pubDate) 또는 ISO 8601(Atom) → KST datetime."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


class NewsSource:
    key = "base"
    name = "Base"

    def __init__(self, config: Config) -> None:
        self.config = config

    def fetch(self) -> list[Article]:  # pragma: no cover - 추상
        raise NotImplementedError


class NaverNewsSource(NewsSource):
    key = "naver_news"
    name = "네이버 뉴스"

    def endpoint(self) -> str:
        return self.config.naver_news_endpoint or NEWS_ENDPOINTS[self.config.naver_api_mode]

    def fetch(self) -> list[Article]:
        out: list[Article] = []
        for q in self.config.g0_queries or DEFAULT_QUERIES:
            params = {"query": q, "display": 100, "start": 1, "sort": "date"}
            try:
                data = _http.get_json(self.endpoint(), params=params, headers=naver_headers(self.config))
            except Exception as exc:
                print(f"  ⚠️  네이버 뉴스 '{q}' 검색 실패: {exc}")
                continue
            out.extend(parse_naver_news(data.get("items") or [], q))
            _http.polite_sleep(self.config.request_delay_sec)
        return out


def parse_naver_news(items: list[dict], query: str) -> list[Article]:
    out = []
    for item in items:
        link = item.get("originallink") or item.get("link") or ""
        if not link:
            continue
        out.append(
            Article(
                title=clean(item.get("title", "")),
                url=link,
                naver_url=item.get("link", "") if "news.naver.com" in item.get("link", "") else "",
                published=parse_date(item.get("pubDate", "")),
                description=clean(item.get("description", "")),
                source="naver_news",
                query=query,
            )
        )
    return out


class RssSource(NewsSource):
    key = "rss"
    name = "의료 전문지 RSS"

    def fetch(self) -> list[Article]:
        out: list[Article] = []
        for feed in self.config.g0_rss_feeds:
            try:
                xml = _http.get_text(feed, headers={"User-Agent": self.config.user_agent})
            except Exception as exc:
                print(f"  ⚠️  RSS 읽기 실패 {feed}: {exc}")
                continue
            out.extend(parse_feed(xml, feed))
            _http.polite_sleep(self.config.request_delay_sec)
        return out


def parse_feed(xml: str, feed_url: str = "") -> list[Article]:
    """RSS 2.0 <item> 과 Atom <entry> 를 모두 읽는다."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        fields = {c.tag.rsplit("}", 1)[-1]: c for c in el}
        link_el = fields.get("link")
        link = ""
        if link_el is not None:
            link = (link_el.text or "").strip() or link_el.get("href", "")
        title = clean(fields["title"].text if "title" in fields else "")
        if not link or not title:
            continue
        # Element는 자식이 없으면 거짓으로 평가되므로 `or` 대신 None 여부로 고른다
        date_el = _first(fields, "pubDate", "published", "updated", "date")
        desc_el = _first(fields, "description", "summary")
        out.append(
            Article(
                title=title,
                url=link,
                published=parse_date(date_el.text if date_el is not None else ""),
                description=clean(desc_el.text if desc_el is not None else ""),
                source="rss",
                query=feed_url,
            )
        )
    return out


def _first(fields: dict, *names: str):
    return next((fields[n] for n in names if fields.get(n) is not None), None)


class SampleNewsSource(NewsSource):
    key = "sample"
    name = "샘플(오프라인)"

    def __init__(self, config: Config, now: datetime | None = None) -> None:
        super().__init__(config)
        self.now = now or datetime.now(KST)

    def fetch(self) -> list[Article]:
        rows = json.loads((self.config.sample_dir / "news_sample.json").read_text(encoding="utf-8"))
        return [
            Article(
                title=r["title"],
                url=r["url"],
                published=self.now - timedelta(hours=r["hours_ago"]),
                description=r.get("description", ""),
                source="sample",
                query=r.get("query", ""),
            )
            for r in rows
        ]


_REGISTRY: dict[str, type[NewsSource]] = {
    "sample": SampleNewsSource,
    "naver_news": NaverNewsSource,
    "rss": RssSource,
}


def get_news_sources(config: Config, now: datetime | None = None) -> list[NewsSource]:
    out: list[NewsSource] = []
    for key in config.enabled_g0_source_keys():
        cls = _REGISTRY.get(key)
        if cls is None:
            raise ValueError(f"알 수 없는 G0 소스 키: {key} (등록된 키: {list(_REGISTRY)})")
        out.append(cls(config, now) if cls is SampleNewsSource else cls(config))
    return out


def available_news_keys() -> list[str]:
    return list(_REGISTRY)
