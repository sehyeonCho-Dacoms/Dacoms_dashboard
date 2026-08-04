"""수집 오케스트레이션: 활성 소스를 순회하며 통일 성과 데이터를 모은다.

한 소스가 실패해도 나머지는 계속 진행한다(부분 실패 허용).
"""

from __future__ import annotations

from .config import Config
from .models import CardNewsMetric
from .sources import get_sources


def collect(config: Config) -> tuple[list[CardNewsMetric], dict[str, int]]:
    metrics: list[CardNewsMetric] = []
    per_source: dict[str, int] = {}
    for source in get_sources(config):
        try:
            got = source.collect()
        except Exception as e:
            per_source[source.key] = -1
            print(f"  ⚠️  [{source.name}] 수집 실패: {e}")
            continue
        per_source[source.key] = len(got)
        metrics.extend(got)
        print(f"  • [{source.name}] {len(got)}건 수집")
    return metrics, per_source
