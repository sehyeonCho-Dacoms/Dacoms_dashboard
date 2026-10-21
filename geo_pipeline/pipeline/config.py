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
    google_cse_key: Optional[str] = os.getenv("GOOGLE_CSE_KEY")
    google_cse_cx: Optional[str] = os.getenv("GOOGLE_CSE_CX")
    # 사람이 구글 상위 티스토리 글 링크를 붙여 넣는 CSV (group,keyword,rank,url)
    tistory_urls_csv: Optional[str] = os.getenv("GR_TISTORY_URLS_CSV")

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
