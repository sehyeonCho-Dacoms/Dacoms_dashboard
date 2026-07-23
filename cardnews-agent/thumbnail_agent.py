"""썸네일 에이전트 — 5가지 마케팅 앵글로 Card01 헤드라인을 생성한다.

페르소나·욕구·인지단계를 입력받아, 앵글(공감/공포/이익/편의/사회증거)별로
3줄(공백 제외 7~12자) 헤드라인 + 칩 태그 2개를 생성한다. 각 앵글은
'규칙 검증 → Claude 자기 평가 → 7점 미만이면 재작성'(최대 3회) 루프를 거친
뒤 구글 시트 '카드뉴스 결과물'에 5행으로 저장된다.
"""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from sheet_client import SheetClient, STATUS_THUMBNAIL_APPROVED, STATUS_THUMBNAIL_WAIT
from verify_loop import run_self_eval_loop, validate_headline_rules

ANGLES = ["공감", "공포", "이익", "편의", "사회증거"]

PROMPT_PATH = Path(__file__).parent / "prompts" / "generate_thumbnails.txt"
CONFIG_PATH = Path(__file__).parent / "config.yaml"


class ThumbnailAngle(BaseModel):
    headline_lines: list[str] = Field(description="정확히 3줄, 각 줄 공백 제외 7~12자")
    chip_persona: str = Field(description="페르소나 요약 태그")
    chip_content: str = Field(description="콘텐츠 핵심 키워드 태그")
    funnel: str = Field(description="이 앵글이 겨냥하는 퍼널 단계 한 단어")


class SelfEval(BaseModel):
    hook: int = Field(description="후킹력 0~10")
    empathy: int = Field(description="공감도 0~10")
    clarity: int = Field(description="명확성 0~10")
    rule_compliance: int = Field(description="규칙 준수 0~10")
    chip_fit: int = Field(description="칩 적합성 0~10")
    overall: float = Field(description="종합 점수 0~10 (위 5개 평균 또는 종합 판단)")
    comment: str = Field(description="개선이 필요하다면 구체적 코멘트, 아니면 '통과'")


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return {}


def _slugify_persona(persona: str, maxlen: int = 12) -> str:
    s = re.sub(r"\s+", "", persona)
    s = re.sub(r"[^0-9A-Za-z가-힣]", "", s)
    return s[:maxlen] or "페르소나"


def generate_headline_for_angle(
    client, angle: str, persona: str, desire: str, awareness: str, feedback: Optional[str]
) -> dict:
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    user_content = (
        f"앵글: {angle}\n페르소나: {persona}\n욕구: {desire}\n인지단계: {awareness}\n\n"
        f"위 조건으로 '{angle}' 앵글의 썸네일 헤드라인 1개를 작성해 주세요."
    )
    if feedback:
        user_content += f"\n\n[이전 시도 피드백] {feedback}\n이 피드백을 반영해 다시 작성하세요."

    response = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=2000,
        thinking={"type": "adaptive"},
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        output_format=ThumbnailAngle,
    )
    result = response.parsed_output
    if result is None:
        raise RuntimeError(f"Claude 응답 파싱 실패 (angle={angle}, stop_reason={response.stop_reason})")
    return result.model_dump()


def self_evaluate_headline(client, payload: dict, persona: str, desire: str) -> tuple[float, str]:
    lines = "\n".join(payload["headline_lines"])
    prompt = (
        "다음 썸네일 헤드라인을 스스로 평가하세요.\n"
        f"타겟 페르소나: {persona}\n욕구: {desire}\n\n"
        f"헤드라인:\n{lines}\n칩1(페르소나): {payload['chip_persona']}\n"
        f"칩2(콘텐츠): {payload['chip_content']}\n\n"
        "후킹력, 공감도, 명확성, 규칙 준수, 칩 적합성을 각 10점 만점으로 채점하고 "
        "종합 점수(overall)를 매기세요. 7점 미만이면 comment에 구체적 개선점을 쓰세요."
    )
    response = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=1000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
        output_format=SelfEval,
    )
    result = response.parsed_output
    if result is None:
        return 0.0, "자기 평가 파싱 실패"
    return result.overall, result.comment


def generate_thumbnails(
    persona: str, desire: str, awareness: str, auto: bool = False, client=None
) -> list[dict]:
    """5개 앵글 헤드라인을 생성하고 시트에 저장할 row dict 리스트를 반환."""
    import anthropic

    client = client or anthropic.Anthropic()
    today = date.today().isoformat()
    folder_name = f"{today}_{_slugify_persona(persona)}"

    print("🎯 썸네일 에이전트 시작 — 5개 앵글 헤드라인 생성")
    rows = []
    for angle in ANGLES:
        def _generate(feedback, angle=angle):
            return generate_headline_for_angle(client, angle, persona, desire, awareness, feedback)

        def _validate(payload):
            ok, reason = validate_headline_rules(payload["headline_lines"])
            if ok:
                print("  ✅ 규칙 검증 통과")
            return ok, reason

        def _evaluate(payload):
            print("  🔍 Claude 자기 평가 중...")
            return self_evaluate_headline(client, payload, persona, desire)

        result = run_self_eval_loop(_generate, _evaluate, _validate)
        payload = result.payload
        status = STATUS_THUMBNAIL_APPROVED if auto else STATUS_THUMBNAIL_WAIT

        rows.append(
            {
                "날짜": today,
                "폴더명": folder_name,
                "페르소나": persona,
                "욕구": desire,
                "인지단계": awareness,
                "펀넬": payload.get("funnel", ""),
                "앵글": angle,
                "Card01 헤드라인": "\n".join(payload.get("headline_lines", [])),
                "Card01 칩1": payload.get("chip_persona", ""),
                "Card01 칩2": payload.get("chip_content", ""),
                "썸네일 상태": status,
            }
        )
        print(f"  [{angle}] 점수 {result.score}/10 (시도 {result.attempts}회, 통과={result.passed})")

    sheet = SheetClient()
    sheet.ensure_headers()
    sheet.append_rows(rows)
    print(f"✅ 저장 완료 — 구글 시트에 {len(rows)}행 저장됨")
    if auto:
        print("🤖 [자동 승인] --auto 모드로 5개 앵글 모두 '썸네일 승인' 처리됨")

    return rows


def main():
    parser = argparse.ArgumentParser(description="썸네일 에이전트")
    parser.add_argument("--persona", required=True)
    parser.add_argument("--desire", required=True)
    parser.add_argument(
        "--awareness",
        default="problem-aware",
        choices=["unaware", "problem-aware", "solution-aware", "product-aware"],
    )
    parser.add_argument("--auto", action="store_true")
    args = parser.parse_args()
    try:
        generate_thumbnails(args.persona, args.desire, args.awareness, auto=args.auto)
    except Exception as exc:  # anthropic API 오류 등을 깔끔하게 표시
        print(f"❌ 썸네일 생성 실패: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
