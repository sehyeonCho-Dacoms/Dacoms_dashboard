"""소스 어댑터 공통 인터페이스와 정규화 헬퍼.

각 소스는 `fetch()`로 자기 플랫폼의 원천(raw dict) 목록을 가져오고,
`normalize()`로 통일 `JobPosting` 하나로 변환한다. 수집(collect)은 이 둘을
묶어 실행하며, 개별 항목 파싱 실패가 전체를 막지 않도록 방어한다.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..config import Config
from ..models import JobPosting
from ..taxonomy import infer_sector, infer_size, normalize_role


@runtime_checkable
class Source(Protocol):
    key: str
    name: str

    def __init__(self, config: Config) -> None: ...

    def fetch(self) -> list[dict]:
        """플랫폼 원천 데이터(raw dict) 목록을 반환."""
        ...

    def normalize(self, raw: dict) -> JobPosting | None:
        """raw dict 하나 → JobPosting. 무효 항목은 None."""
        ...


class BaseSource:
    """공통 기능을 담은 베이스. 각 소스는 이걸 상속해 fetch/normalize 구현."""

    key: str = "base"
    name: str = "Base"

    def __init__(self, config: Config) -> None:
        self.config = config

    # 하위 클래스에서 구현
    def fetch(self) -> list[dict]:  # pragma: no cover - 추상
        raise NotImplementedError

    def normalize(self, raw: dict) -> JobPosting | None:  # pragma: no cover - 추상
        raise NotImplementedError

    def collect(self) -> list[JobPosting]:
        """fetch → normalize 파이프. 개별 파싱 오류는 건너뛴다."""
        out: list[JobPosting] = []
        for raw in self.fetch():
            try:
                job = self.normalize(raw)
            except Exception:
                job = None
            if job and job.company and job.title:
                out.append(job)
        return out

    # 정규화 공통 헬퍼 -------------------------------------------------------
    def enrich(self, job: JobPosting) -> JobPosting:
        """직무/섹터/규모를 taxonomy로 보강한다(소스가 못 준 필드 채움)."""
        if job.role in ("", "기타"):
            job.role = normalize_role(job.title, job.description)
        if not job.sector:
            job.sector = infer_sector(job.company, job.title, job.description)
        job.company_size = infer_size(job.company_size, job.company, job.description)
        return job
