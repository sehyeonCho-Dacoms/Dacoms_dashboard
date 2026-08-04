"""metrics-analyzer 서브에이전트가 읽는 CSV 생성.

test-data/dummy-metrics.csv 와 동일한 컬럼 스키마를 유지해, 더미 데이터로
검증한 metrics-analyzer 지침이 실데이터에도 그대로 적용되게 한다.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .models import CSV_FIELDS, CardNewsMetric


def write_metrics_csv(path: Path, metrics: list[CardNewsMetric]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(metrics, key=lambda m: m.date or "", reverse=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for m in rows:
            writer.writerow(m.to_csv_row())


def unregistered_post_ids(metrics: list[CardNewsMetric]) -> list[str]:
    """post_registry.csv에 없어 topic/sport_category/format이 비어 있는 게시물."""
    return [m.post_id for m in metrics if not m.registered]
