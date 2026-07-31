"""수집 오케스트레이션: 활성 소스를 순회하며 통일 공고를 모은다.

한 소스가 실패해도 나머지는 계속 진행한다(부분 실패 허용).
"""

from __future__ import annotations

from .config import Config
from .models import JobPosting
from .sources import get_sources


def collect(config: Config) -> tuple[list[JobPosting], dict[str, int]]:
    """(수집된 공고, 소스별 건수) 반환."""
    jobs: list[JobPosting] = []
    per_source: dict[str, int] = {}
    for source in get_sources(config):
        try:
            got = source.collect()
        except Exception as e:  # 소스 단위 실패 격리
            per_source[source.key] = -1
            print(f"  ⚠️  [{source.name}] 수집 실패: {e}")
            continue
        per_source[source.key] = len(got)
        jobs.extend(got)
        print(f"  • [{source.name}] {len(got)}건 수집")
    return jobs, per_source
