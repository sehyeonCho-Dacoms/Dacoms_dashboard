"""환경변수 기반 설정 로더.

키가 없으면 해당 소스는 자동으로 건너뛴다(에러 대신 skip). 자격증명이 전혀
없어도 `sample` 소스로 전체 노드가 오프라인 동작한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv 미설치 시 무시
    pass


def _split(csv: str | None) -> list[str]:
    return [x.strip() for x in (csv or "").split(",") if x.strip()]


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() == "true"


@dataclass
class Config:
    """G-R 노드 실행 설정."""

    # 활성화할 소스 (쉼표구분). 기본은 오프라인 sample.
    sources: list[str] = field(default_factory=lambda: _split(os.getenv("GR_SOURCES", "sample")))

    top_n: int = int(os.getenv("GR_TOP_N", "5"))                 # 검색어당 상위 N개
    with_modifiers: bool = _flag("GR_WITH_MODIFIERS")            # 2차(수식어) 수집 여부

    # 글 페이지를 열어 구조 지표를 자동 측정할지. 이용약관 확인 후에만 true.
    # false면 목록(제목·링크·발행일)만 남기고 구조 칸은 '사람 기록'으로 둔다.
    fetch_pages: bool = _flag("GR_FETCH_PAGES")

    # ── 소스별 자격증명 ─────────────────────────
    naver_client_id: Optional[str] = os.getenv("NAVER_CLIENT_ID")
    naver_client_secret: Optional[str] = os.getenv("NAVER_CLIENT_SECRET")
    # hub = 네이버 클라우드 NAVER API HUB (기본) / legacy = 네이버 개발자센터
    naver_api_mode: str = os.getenv("NAVER_API_MODE", "hub").lower()
    naver_blog_endpoint: Optional[str] = os.getenv("NAVER_BLOG_ENDPOINT")  # 주소가 다를 때만
    # 네이버 블로그 검색에 섞여 나오는 티스토리 글을 티스토리 채널로 기록 (구글 API 대체)
    tistory_from_naver: bool = _flag("GR_TISTORY_FROM_NAVER", "true")
    google_cse_key: Optional[str] = os.getenv("GOOGLE_CSE_KEY")
    google_cse_cx: Optional[str] = os.getenv("GOOGLE_CSE_CX")
    # 사람이 구글 상위 티스토리 글 링크를 붙여 넣는 CSV (group,keyword,rank,url)
    tistory_urls_csv: Optional[str] = os.getenv("GR_TISTORY_URLS_CSV")

    # ── G0 이슈 트래커 ──────────────────────────
    # 소스: naver_news(네이버 뉴스 검색 API) · rss(G0_RSS_FEEDS) · sample
    g0_sources: list[str] = field(default_factory=lambda: _split(os.getenv("G0_SOURCES", "sample")))
    g0_max: int = int(os.getenv("G0_MAX", "100"))                    # 하루 최대 N건 (체인 v1)
    g0_window_hours: int = int(os.getenv("G0_WINDOW_HOURS", "26"))   # 하루 1회 + 여유 2시간
    # 수집 검색어. 비우면 news.py 기본값. 키워드로 미리 거르지 않고 넓게 모은다(10/16 합의)
    g0_queries: list[str] = field(default_factory=lambda: _split(os.getenv("G0_QUERIES")))
    g0_rss_feeds: list[str] = field(default_factory=lambda: _split(os.getenv("G0_RSS_FEEDS")))
    naver_news_endpoint: Optional[str] = os.getenv("NAVER_NEWS_ENDPOINT")  # 주소가 다를 때만

    # HTTP 매너
    request_delay_sec: float = float(os.getenv("REQUEST_DELAY_SEC", "2.0"))
    user_agent: str = os.getenv(
        "HTTP_USER_AGENT",
        "DoctorOnGeoBot/0.1 (+https://doctoronhr.tistory.com)",
    )

    # ── 경로 ────────────────────────────────────
    out_dir: Path = field(default_factory=lambda: Path(os.getenv("GR_OUT_DIR", "geo_pipeline/out")))
    sample_dir: Path = field(
        default_factory=lambda: Path(os.getenv("GR_SAMPLE_DIR", "geo_pipeline/sample_data"))
    )

    def enabled_source_keys(self) -> list[str]:
        """설정상 실제 동작 가능한 소스만 남긴다(자격증명 체크)."""
        out = []
        for key in self.sources:
            if key == "naver" and not (self.naver_client_id and self.naver_client_secret):
                continue
            if key == "tistory_cse" and not (self.google_cse_key and self.google_cse_cx):
                continue
            if key == "tistory_manual" and not self.tistory_urls_csv:
                continue
            out.append(key)
        return out or ["sample"]

    def enabled_g0_source_keys(self) -> list[str]:
        out = []
        for key in self.g0_sources:
            if key == "naver_news" and not (self.naver_client_id and self.naver_client_secret):
                continue
            if key == "rss" and not self.g0_rss_feeds:
                continue
            out.append(key)
        return out or ["sample"]
