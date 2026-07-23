"""환경변수 기반 설정 로더.

키가 없으면 해당 소스는 자동으로 건너뛴다(에러 대신 skip). 자격증명이 전혀
없어도 `sample` 소스로 전체 파이프라인이 오프라인 동작하도록 설계했다.
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


@dataclass
class Config:
    """파이프라인 실행 설정."""

    # 활성화할 소스 목록 (쉼표구분). 기본은 오프라인 sample.
    sources: list[str] = field(
        default_factory=lambda: _split(os.getenv("JOB_SOURCES", "sample"))
    )

    # 수집 키워드 (쉼표구분) — 스포츠 산업 중심
    keywords: list[str] = field(
        default_factory=lambda: _split(
            os.getenv("JOB_KEYWORDS", "스포츠,피트니스,골프,구단,스포츠마케팅")
        )
    )
    per_source_limit: int = int(os.getenv("JOB_PER_SOURCE_LIMIT", "50"))

    # ── 소스별 자격증명 ─────────────────────────
    saramin_access_key: Optional[str] = os.getenv("SARAMIN_ACCESS_KEY")
    worknet_auth_key: Optional[str] = os.getenv("WORKNET_AUTH_KEY")
    # 원티드 크롤러 사용 동의 (ToS 확인 후 true로) — 기본 비활성
    wanted_enabled: bool = os.getenv("WANTED_CRAWLER_ENABLED", "false").lower() == "true"

    # HTTP 매너 (크롤러 rate-limit)
    request_delay_sec: float = float(os.getenv("REQUEST_DELAY_SEC", "1.0"))
    user_agent: str = os.getenv(
        "HTTP_USER_AGENT",
        "DraftOnBot/0.1 (+https://drafton.example; contact ops@drafton.example)",
    )

    # ── 경로 ────────────────────────────────────
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("JOB_DATA_DIR", "job_pipeline/data"))
    )
    # 대시보드가 fetch 하는 최종 산출물 (dashboard.html 기준 상대경로 ./data/dashboard.json)
    dashboard_json: Path = field(
        default_factory=lambda: Path(os.getenv("DASHBOARD_JSON", "data/dashboard.json"))
    )
    # 오프라인 sample 소스가 읽는 원천 파일
    sample_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("SAMPLE_RAW_PATH", "job_pipeline/sample_data/raw_sample.json")
        )
    )

    @property
    def store_path(self) -> Path:
        return self.data_dir / "jobs.json"

    def enabled_source_keys(self) -> list[str]:
        """설정상 실제 동작 가능한 소스만 남긴다(자격증명 체크)."""
        out = []
        for key in self.sources:
            if key == "saramin" and not self.saramin_access_key:
                continue
            if key == "worknet" and not self.worknet_auth_key:
                continue
            if key == "wanted" and not self.wanted_enabled:
                continue
            out.append(key)
        return out or ["sample"]
