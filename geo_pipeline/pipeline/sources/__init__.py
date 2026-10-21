"""검색 소스 레지스트리.

새 채널을 붙이려면:
  1) sources/<채널>.py 에 BaseSource 를 상속해 search() 구현
  2) 아래 _REGISTRY 에 등록
그러면 GR_SOURCES 환경변수에 키만 추가해서 즉시 활성화된다.
"""

from __future__ import annotations

from ..config import Config
from .base import BaseSource, RobotsBlocked
from .naver import NaverBlogSource
from .sample import SampleSource
from .tistory import TistoryCseSource, TistoryManualSource

_REGISTRY: dict[str, type[BaseSource]] = {
    "sample": SampleSource,
    "naver": NaverBlogSource,
    "tistory_cse": TistoryCseSource,
    "tistory_manual": TistoryManualSource,
}


def get_sources(config: Config) -> list[BaseSource]:
    """설정에서 활성화 가능한 소스 인스턴스 목록을 만든다."""
    out: list[BaseSource] = []
    for key in config.enabled_source_keys():
        cls = _REGISTRY.get(key)
        if cls is None:
            raise ValueError(f"알 수 없는 소스 키: {key} (등록된 키: {list(_REGISTRY)})")
        out.append(cls(config))
    return out


def available_keys() -> list[str]:
    return list(_REGISTRY)


__all__ = ["BaseSource", "RobotsBlocked", "available_keys", "get_sources"]
