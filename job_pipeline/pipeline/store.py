"""공고 스토어: JSON 파일에 통일 스키마를 저장하고 증분 병합한다.

핵심은 '증분 병합(merge)':
  - 같은 공고(key 동일)는 최신 필드로 갱신하되, 사람이 손댄 워크플로 값
    (job.status, lead.stage)은 유지한다.
  - 새 공고는 status=신규 로 추가.
실서비스에선 SQLite/DB로 교체 가능하나 인터페이스는 동일하게 유지.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import JobPosting


def load_jobs(path: Path) -> list[JobPosting]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [_from_dict(d) for d in data.get("jobs", [])]


def save_jobs(path: Path, jobs: list[JobPosting]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"jobs": [j.to_dict() for j in jobs]}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def merge(existing: list[JobPosting], incoming: list[JobPosting]) -> list[JobPosting]:
    """기존 + 신규를 병합. 워크플로 상태 유지, 나머지는 신규 값으로 갱신."""
    by_key: dict[str, JobPosting] = {j.key: j for j in existing}
    for job in incoming:
        prev = by_key.get(job.key)
        if prev is not None:
            # 사람이 지정한 워크플로 상태는 보존
            job.status = prev.status
        by_key[job.key] = job
    return list(by_key.values())


def prev_open_counts(existing: list[JobPosting]) -> dict[str, int]:
    """직전 스토어의 회사별 공고 수 — 주간 증가폭 계산에 사용."""
    counts: dict[str, int] = {}
    for j in existing:
        counts[j.company] = counts.get(j.company, 0) + 1
    return counts


def _from_dict(d: dict) -> JobPosting:
    known = {
        "source", "source_id", "company", "title", "url", "role", "level",
        "location", "employment_type", "company_size", "sector", "salary",
        "posted_at", "deadline", "description", "drafton_fit", "fit_reasons",
        "status",
    }
    return JobPosting(**{k: v for k, v in d.items() if k in known})
