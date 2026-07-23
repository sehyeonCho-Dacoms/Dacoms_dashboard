"""자기 검증 루프 — 규칙 검증 + Claude 자기 평가 + 재작성.

thumbnail_agent.py와 body_agent.py가 공유하는 순수 로직.
    생성 → 규칙 검증(Python) → 자기 평가(Claude) → 7점 미만이면 재작성(최대 3회)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

MAX_ATTEMPTS = 3
PASS_SCORE = 7


@dataclass
class VerifyResult:
    payload: dict            # 최종(또는 최선) 생성 결과
    score: float             # 마지막 자기 평가 점수
    attempts: int            # 실제 생성 시도 횟수
    passed: bool             # 규칙+점수 통과 여부


def validate_headline_rules(lines: list[str]) -> tuple[bool, str]:
    """헤드라인이 '정확히 3줄, 각 줄 공백 제외 7~12자' 규칙을 지키는지 확인."""
    if len(lines) != 3:
        return False, f"헤드라인은 정확히 3줄이어야 합니다 (현재 {len(lines)}줄)."
    for i, line in enumerate(lines, start=1):
        length = len(line.replace(" ", ""))
        if not (7 <= length <= 12):
            return False, f"{i}번째 줄이 {length}자입니다. 공백 제외 7~12자로 다시 작성하세요."
    return True, ""


def run_self_eval_loop(
    generate: Callable[[Optional[str]], dict],
    evaluate: Callable[[dict], tuple[float, str]],
    validate: Optional[Callable[[dict], tuple[bool, str]]] = None,
    max_attempts: int = MAX_ATTEMPTS,
    pass_score: int = PASS_SCORE,
) -> VerifyResult:
    """생성 → (규칙 검증) → 자기 평가 → 재작성 루프를 실행한다.

    generate(feedback): feedback=None이면 최초 생성, 아니면 피드백을 반영해 재작성.
                         결과 dict를 반환.
    evaluate(payload): (점수, 평가 코멘트) 반환.
    validate(payload): (통과 여부, 실패 사유) 반환. 없으면 규칙 검증 생략.
    """
    best_payload: Optional[dict] = None
    best_score = -1.0
    feedback: Optional[str] = None

    for attempt in range(1, max_attempts + 1):
        payload = generate(feedback)

        if validate is not None:
            ok, reason = validate(payload)
            if not ok:
                feedback = reason
                if best_payload is None:
                    best_payload = payload
                continue

        score, comment = evaluate(payload)
        if score > best_score:
            best_payload, best_score = payload, score

        if score >= pass_score:
            return VerifyResult(payload=payload, score=score, attempts=attempt, passed=True)

        feedback = f"이전 평가 점수 {score}/10. 개선 필요: {comment}"

    return VerifyResult(
        payload=best_payload or {}, score=best_score, attempts=max_attempts, passed=False
    )
