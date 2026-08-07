"""오프라인 샘플 소스.

네트워크·자격증명 없이 파이프라인 전체를 돌려볼 수 있게 로컬 JSON을 읽는다.
Instagram Graph API 응답과 동일한 raw 형태(media + insights)를 흉내 내어,
InstagramSource의 normalize 로직도 함께 검증할 수 있게 한다.
"""

from __future__ import annotations

import json

from .base import BaseSource
from .instagram import normalize_media


class SampleSource(BaseSource):
    key = "sample"
    name = "샘플(오프라인)"

    def fetch(self) -> list[dict]:
        path = self.config.sample_path
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("data", [])

    def normalize(self, raw: dict):
        metric = normalize_media(raw)
        if metric is None:
            return None
        return self.apply_registry(metric)
