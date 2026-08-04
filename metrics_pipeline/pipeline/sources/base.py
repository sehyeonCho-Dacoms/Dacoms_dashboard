"""소스 어댑터 공통 인터페이스.

job_pipeline/pipeline/sources/base.py 와 동일한 패턴: fetch() → normalize()를
묶어 collect()로 실행하며, 개별 항목 파싱 실패가 전체를 막지 않는다.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..config import Config
from ..models import CardNewsMetric
from ..registry import load_registry


@runtime_checkable
class Source(Protocol):
    key: str
    name: str

    def __init__(self, config: Config) -> None: ...

    def fetch(self) -> list[dict]:
        """플랫폼 원천 데이터(raw dict) 목록을 반환."""
        ...

    def normalize(self, raw: dict) -> CardNewsMetric | None:
        """raw dict 하나 → CardNewsMetric. 무효 항목은 None."""
        ...


class BaseSource:
    key: str = "base"
    name: str = "Base"

    def __init__(self, config: Config) -> None:
        self.config = config
        self._registry = load_registry(config.post_registry_path)

    def fetch(self) -> list[dict]:  # pragma: no cover - 추상
        raise NotImplementedError

    def normalize(self, raw: dict) -> CardNewsMetric | None:  # pragma: no cover - 추상
        raise NotImplementedError

    def collect(self) -> list[CardNewsMetric]:
        out: list[CardNewsMetric] = []
        for raw in self.fetch():
            try:
                metric = self.normalize(raw)
            except Exception:
                metric = None
            if metric and metric.post_id:
                out.append(metric)
        return out

    def apply_registry(self, metric: CardNewsMetric) -> CardNewsMetric:
        """post_registry.csv에서 topic/sport_category/format을 채운다.

        미등록 게시물은 값을 비워둔 채 registered=False로 표시하고
        data_gaps에 사유를 남긴다 — 임의로 추측해 채우지 않는다.
        """
        entry = self._registry.get(metric.post_id)
        if entry:
            metric.topic = entry["topic"]
            metric.sport_category = entry["sport_category"]
            metric.format = entry["format"]
            metric.registered = True
        else:
            metric.registered = False
            metric.data_gaps.append(
                "post_registry.csv에 미등록 — topic/sport_category/format 확보 불가. "
                "게시 담당자가 post_id를 레지스트리에 기록해야 함."
            )
        return metric
