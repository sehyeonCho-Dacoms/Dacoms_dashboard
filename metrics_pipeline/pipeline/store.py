"""성과 스토어: JSON 파일에 통일 스키마를 저장하고 증분 병합한다.

job_pipeline/pipeline/store.py 와 동일한 패턴 — 같은 게시물(post_id)은 최신
값으로 갱신, 새 게시물은 추가. 이 스토어가 쌓일수록 전주/전월 대비 변화율을
계산할 히스토리가 생긴다.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import CardNewsMetric


def load_metrics(path: Path) -> list[CardNewsMetric]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [_from_dict(d) for d in data.get("metrics", [])]


def save_metrics(path: Path, metrics: list[CardNewsMetric]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"metrics": [m.to_dict() for m in metrics]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def merge(existing: list[CardNewsMetric], incoming: list[CardNewsMetric]) -> list[CardNewsMetric]:
    by_key: dict[str, CardNewsMetric] = {m.post_id: m for m in existing}
    for metric in incoming:
        by_key[metric.post_id] = metric  # 성과 수치는 항상 최신 값으로 덮어씀
    return list(by_key.values())


def _from_dict(d: dict) -> CardNewsMetric:
    known = {
        "post_id", "date", "permalink", "topic", "sport_category", "format",
        "registered", "reach", "saves", "shares", "likes", "comments",
        "impressions", "profile_visits", "clicks", "apply_clicks", "data_gaps",
    }
    return CardNewsMetric(**{k: v for k, v in d.items() if k in known})
