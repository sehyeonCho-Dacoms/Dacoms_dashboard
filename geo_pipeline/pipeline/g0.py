"""G0 이슈 트래커 (DR-MKT-01) — 매일 10시 · AI · 하루 최대 100건.

  뉴스 소스(네이버 뉴스 API·RSS) → 수집 창(최근 G0_WINDOW_HOURS) → 중복 제거
  → 1차 거름망(screen.py) → 통과 기사 먼저·최신순 최대 G0_MAX건 → 기사 목록(JSON·CSV·MD)

상한을 거름망 뒤에 둔다. 앞에 두면 최신 일반 기사가 100건을 채워 쓸 만한 기사가 잘린다.

출력은 G2 흥미도 점수의 입력이다. 기사 본문은 받지 않고 제목·원문 링크만 남긴다
(API 요약은 거름망 판단에만 쓰고 산출물에는 넣지 않는다 — export.G0_OMIT_FIELDS).
"""

from __future__ import annotations

import hashlib
import urllib.parse
from datetime import datetime, timedelta

from .config import Config
from .models import SCREEN_PASS, Article
from .screen import screen, title_key
from .sources.news import KST, get_news_sources


def run_g0(config: Config, now: datetime | None = None, stats: dict | None = None) -> list[Article]:
    """stats 를 넘기면 단계별 건수(수집·창·중복 제거·통과)를 채운다 (요약 MD 첫 줄용)."""
    now = now or datetime.now(KST)
    raw: list[Article] = []
    for source in get_news_sources(config, now):
        got = source.fetch()
        print(f"🔎 {source.name}: {len(got)}건")
        raw.extend(got)

    since = now - timedelta(hours=config.g0_window_hours)
    recent = [a for a in raw if a.published is None or a.published >= since]
    articles = dedupe(recent)
    for a in articles:
        a.press = urllib.parse.urlsplit(a.url).netloc.removeprefix("www.")
        a.id = article_id(a, now)
        screen(a, now)
    passed = sum(1 for a in articles if a.screen == SCREEN_PASS)
    if stats is not None:
        stats.update(raw=len(raw), recent=len(recent), deduped=len(articles), passed=passed,
                     hours=config.g0_window_hours)
    print(f"📰 수집 {len(raw)} → 최근 {config.g0_window_hours}시간 {len(recent)} → 중복 제거 {len(articles)}"
          f" (거름망 통과 {passed}) → 최대 {config.g0_max}건")

    articles.sort(key=lambda a: (a.screen == SCREEN_PASS, a.published or now), reverse=True)
    return articles[: config.g0_max]


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
