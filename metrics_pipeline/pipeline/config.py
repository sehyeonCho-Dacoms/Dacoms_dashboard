"""환경변수 기반 설정 로더.

job_pipeline/pipeline/config.py 와 동일한 철학: 자격증명이 없으면 해당 소스는
자동으로 건너뛰고 `sample`로 오프라인 동작한다.
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


# Meta Graph API가 미디어 인사이트로 실제 지원하는 지표 후보.
# 미디어 타입(FEED/REELS/STORY)이나 API 버전에 따라 일부는 거부될 수 있어
# collect 단계에서 지표 단위로 개별 재시도한다 (전부 한 번에 실패시키지 않음).
DEFAULT_IG_METRICS = "reach,saved,shares,likes,comments,total_interactions,profile_activity"


@dataclass
class Config:
    """파이프라인 실행 설정."""

    sources: list[str] = field(
        default_factory=lambda: _split(os.getenv("METRICS_SOURCES", "sample"))
    )

    # ── 인스타그램(Meta Graph API) 자격증명 ─────────────
    ig_access_token: Optional[str] = os.getenv("IG_ACCESS_TOKEN")
    ig_business_account_id: Optional[str] = os.getenv("IG_BUSINESS_ACCOUNT_ID")
    ig_api_version: str = os.getenv("IG_API_VERSION", "v21.0")
    ig_metrics: list[str] = field(
        default_factory=lambda: _split(os.getenv("IG_INSIGHTS_METRICS", DEFAULT_IG_METRICS))
    )
    # 최근 며칠치 미디어만 조회할지 (증분 수집)
    ig_lookback_days: int = int(os.getenv("IG_LOOKBACK_DAYS", "35"))

    # HTTP 매너
    request_delay_sec: float = float(os.getenv("REQUEST_DELAY_SEC", "0.5"))

    # ── 게시물 메타데이터 레지스트리 ─────────────────────
    # Instagram API는 "주제/종목/카드뉴스 유형"을 모른다 — 게시 담당자가
    # post_id ↔ topic/sport_category/format/apply_clicks를 직접 기록해야 한다.
    # (card-news-designer가 만든 asset_files/게시 이후 사람이 채워 넣는 값)
    post_registry_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("POST_REGISTRY_PATH", "metrics_pipeline/data/post_registry.csv")
        )
    )

    # ── 경로 ────────────────────────────────────
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("METRICS_DATA_DIR", "metrics_pipeline/data"))
    )
    # metrics-analyzer 에이전트가 읽는 최종 산출물
    metrics_csv: Path = field(
        default_factory=lambda: Path(os.getenv("METRICS_CSV", "data/card_news_metrics.csv"))
    )
    sample_path: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "SAMPLE_RAW_PATH",
                "metrics_pipeline/sample_data/raw_metrics_sample.json",
            )
        )
    )

    @property
    def store_path(self) -> Path:
        return self.data_dir / "metrics.json"

    def enabled_source_keys(self) -> list[str]:
        """자격증명 체크 후 실제 동작 가능한 소스만 남긴다."""
        out = []
        for key in self.sources:
            if key == "instagram" and not (self.ig_access_token and self.ig_business_account_id):
                continue
            out.append(key)
        return out or ["sample"]
