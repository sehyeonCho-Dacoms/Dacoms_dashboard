"""소스 어댑터 레지스트리.

새 SNS 채널을 붙이려면:
  1) sources/<채널>.py 에 fetch_raw()/normalize() 구현
  2) 아래 _REGISTRY 에 등록
그러면 METRICS_SOURCES 환경변수에 키만 추가해서 즉시 활성화된다.
"""

from __future__ import annotations

from ..config import Config
from .base import Source
from .instagram import InstagramSource
from .sample import SampleSource

_REGISTRY: dict[str, type[Source]] = {
    "sample": SampleSource,
    "instagram": InstagramSource,
}


def get_sources(config: Config) -> list[Source]:
    out: list[Source] = []
    for key in config.enabled_source_keys():
        cls = _REGISTRY.get(key)
        if cls is None:
            raise ValueError(f"알 수 없는 소스 키: {key} (등록된 키: {list(_REGISTRY)})")
        out.append(cls(config))
    return out


def available_keys() -> list[str]:
    return list(_REGISTRY)
