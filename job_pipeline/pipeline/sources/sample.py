"""오프라인 샘플 소스.

네트워크·자격증명 없이 파이프라인 전체를 돌려볼 수 있게 로컬 JSON을 읽는다.
테스트와 데모의 기본 소스이며, 실제 API 응답과 동일한 raw 형태를 흉내 낸다.
"""

from __future__ import annotations

import json

from ..models import JobPosting
from .base import BaseSource


class SampleSource(BaseSource):
    key = "sample"
    name = "샘플(오프라인)"

    def fetch(self) -> list[dict]:
        path = self.config.sample_path
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("items", [])

    def normalize(self, raw: dict) -> JobPosting | None:
        job = JobPosting(
            source=self.key,
            source_id=str(raw.get("id", "")),
            company=raw.get("company", "").strip(),
            title=raw.get("title", "").strip(),
            url=raw.get("url", ""),
            role=raw.get("role", ""),
            level=raw.get("level", "경력무관"),
            location=raw.get("location", ""),
            employment_type=raw.get("employmentType", ""),
            company_size=raw.get("size", ""),
            sector=raw.get("sector", ""),
            salary=raw.get("salary", ""),
            posted_at=raw.get("postedAt", ""),
            description=raw.get("description", ""),
            raw=raw,
        )
        return self.enrich(job)
