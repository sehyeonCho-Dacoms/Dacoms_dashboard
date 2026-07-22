"""파이프라인 전반에서 주고받는 데이터 구조 정의."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Topic:
    """시트 입력 탭의 한 행: 카드뉴스 주제와 타겟 페르소나."""

    id: str
    topic: str
    persona: str
    status: str = ""          # 예: "" | "처리됨"
    row_index: Optional[int] = None  # 구글 시트 행 번호(1-based). 로컬 백엔드는 None.

    @property
    def is_processed(self) -> bool:
        return self.status.strip() == "처리됨"

    def to_row(self) -> list[str]:
        """주제입력 탭에 기입할 순서대로 값을 반환 (TOPIC_HEADERS 순서와 일치)."""
        return [self.id, self.topic, self.persona, self.status]


_TOPIC_ID_RE = re.compile(r"^T(\d+)$")


def next_topic_ids(existing_ids: list[str], count: int) -> list[str]:
    """기존 ID(T001, T002, ...) 중 최댓값 다음부터 count개의 새 ID를 생성."""
    max_n = 0
    for tid in existing_ids:
        m = _TOPIC_ID_RE.match(tid.strip())
        if m:
            max_n = max(max_n, int(m.group(1)))
    return [f"T{max_n + i:03d}" for i in range(1, count + 1)]


@dataclass
class CopyAngle:
    """하나의 주제에 대해 생성된 한 개의 P.D.A. 카피 앵글."""

    topic_id: str
    topic: str
    persona: str
    angle_name: str        # 앵글명 (예: 공감형, 정보형)
    angle_description: str  # 앵글 설명
    hook: str              # 표지 후킹 문구
    problem: str           # P — 문제(Problem)
    desire: str            # D — 욕망/기대(Desire)
    action: str            # A — 행동(Action)
    cta: str               # 마지막 카드 CTA
    image_prompt: str      # 표지 이미지 생성용 프롬프트(영문 권장)
    approved: bool = False  # 담당자 '승인' 여부
    row_index: Optional[int] = None

    def to_row(self) -> list[str]:
        """구글 시트/CSV 초안 탭에 기입할 순서대로 값을 반환."""
        return [
            self.topic_id,
            self.topic,
            self.persona,
            self.angle_name,
            self.angle_description,
            self.hook,
            self.problem,
            self.desire,
            self.action,
            self.cta,
            self.image_prompt,
            "승인" if self.approved else "",
        ]

    def to_dict(self) -> dict:
        return asdict(self)


# 초안 탭의 헤더 (to_row 순서와 반드시 일치)
DRAFT_HEADERS: list[str] = [
    "주제ID",
    "주제",
    "페르소나",
    "앵글명",
    "앵글설명",
    "후킹",
    "문제(P)",
    "욕망(D)",
    "행동(A)",
    "CTA",
    "이미지프롬프트",
    "승인",
]

# 입력 탭의 헤더
TOPIC_HEADERS: list[str] = ["ID", "주제", "타겟페르소나", "상태"]

# '승인'으로 인정하는 셀 값 (대소문자·공백 무시 비교)
APPROVED_VALUES = {"승인", "approved", "true", "y", "yes", "o", "ok", "✓"}


def is_approved_value(cell: str) -> bool:
    return str(cell).strip().lower() in APPROVED_VALUES
