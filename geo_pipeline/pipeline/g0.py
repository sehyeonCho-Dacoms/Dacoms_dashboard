"""G0 이슈 트래커 (DR-MKT-01) — 매일 10시 · AI · 하루 최대 100건.

  뉴스 소스(네이버 뉴스 API·RSS) → 수집 창(최근 G0_WINDOW_HOURS) → 중복 제거
  → 최신순 최대 G0_MAX건 → 1차 거름망(screen.py) → 기사 목록(JSON·CSV·MD)

출력은 G2 흥미도 점수의 입력이다. 기사 본문은 받지 않고 제목·원문 링크·API 요약만 남긴다.
"""

from __future__ import annotations

import hashlib
import urllib.parse
from datetime import datetime, timedelta

from .config import Config
from .models import SCREEN_PASS, Article
from .screen import screen, title_key
from .sources.news import KST, get_news_sources


def run_g0(config: Config, now: datetime | None = None) -> list[Article]:
    now = now or datetime.now(KST)
    raw: list[Article] = []
    for source in get_news_sources(config, now):
        got = source.fetch()
        print(f"🔎 {source.name}: {len(got)}건")
        raw.extend(got)

    since = now - timedelta(hours=config.g0_window_hours)
    recent = [a for a in raw if a.published is None or a.published >= since]
    articles = dedupe(recent)
    articles.sort(key=lambda a: a.published or now, reverse=True)
    articles = articles[: config.g0_max]

    for a in articles:
        a.press = urllib.parse.urlsplit(a.url).netloc.removeprefix("www.")
        a.id = article_id(a, now)
        screen(a, now)
    passed = sum(1 for a in articles if a.screen == SCREEN_PASS)
    print(f"📰 수집 {len(raw)} → 최근 {config.g0_window_hours}시간 {len(recent)} → 중복 제거·상한 {len(articles)}"
          f" → 거름망 통과 {passed}")
    return articles


def dedupe(articles: list[Article]) -> list[Article]:
    """같은 원문 링크, 또는 같은 제목(다른 검색어·매체 재전송)은 한 건만 남긴다."""
    seen_url: set[str] = set()
    seen_title: set[str] = set()
    out = []
    for a in articles:
        u = a.url.split("?")[0].rstrip("/")
        k = title_key(a.title)
        if u in seen_url or (k and k in seen_title):
            continue
        seen_url.add(u)
        seen_title.add(k)
        out.append(a)
    return out


def article_id(a: Article, now: datetime) -> str:
    day = (a.published or now).strftime("%Y%m%d")
    return f"N-{day}-{hashlib.sha1(a.url.encode()).hexdigest()[:4]}"
