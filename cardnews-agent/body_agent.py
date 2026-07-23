"""본문 에이전트 — 승인된 썸네일을 이어 Card02~05 본문·CTA를 생성한다.

구글 시트에서 '썸네일 승인'이면서 아직 본문이 없는 행을 읽어와, 헤드라인의
톤을 이어받아 Card02~04 섹션타이틀+인풋텍스트, Card05 CTA, 컨셉, 기대반응을
생성한다. 썸네일 톤과의 일관성을 Claude가 자기 평가(10점 만점, 7점 미만이면
재작성)한 뒤 같은 행의 L~U열에 저장한다.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from sheet_client import SheetClient, STATUS_BODY_APPROVED, STATUS_BODY_WAIT, STATUS_THUMBNAIL_APPROVED

PROMPT_PATH = Path(__file__).parent / "prompts" / "generate_body.txt"


class BodyContent(BaseModel):
    card02_title: str
    card02_text: str
    card03_title: str
    card03_text: str
    card04_title: str
    card04_text: str
    cta: str
    concept: str = Field(description="이 본문 세트를 관통하는 한 줄 컨셉")
    expected_reaction: str = Field(description="독자의 기대 반응 한 줄")


class ToneEval(BaseModel):
    tone_consistency: float = Field(description="썸네일과의 톤 일관성 0~10")
    comment: str = Field(description="7점 미만이면 구체적 개선점, 아니면 '통과'")


def _validate_body(payload: dict) -> tuple[bool, str]:
    required = [
        "card02_title", "card02_text", "card03_title", "card03_text",
        "card04_title", "card04_text", "cta",
    ]
    for key in required:
        value = payload.get(key, "").strip()
        if not value:
            return False, f"{key} 항목이 비어 있습니다."
    for key in ["card02_text", "card03_text", "card04_text"]:
        if len(payload[key]) < 10:
            return False, f"{key}가 너무 짧습니다 (최소 10자 이상, 2~4문장 권장)."
    return True, ""


def generate_body_for_row(client, row: dict, feedback: Optional[str] = None) -> dict:
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    headline = row.get("Card01 헤드라인", "").replace("\n", " / ")
    user_content = (
        f"앵글: {row.get('앵글', '')}\n"
        f"썸네일 헤드라인: {headline}\n"
        f"페르소나: {row.get('페르소나', '')}\n욕구: {row.get('욕구', '')}\n\n"
        "위 썸네일의 흐름과 톤을 이어받아 본문(Card02~04)과 CTA(Card05)를 작성하세요."
    )
    if feedback:
        user_content += f"\n\n[이전 시도 피드백] {feedback}\n이 피드백을 반영해 다시 작성하세요."

    response = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=3000,
        thinking={"type": "adaptive"},
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        output_format=BodyContent,
    )
    result = response.parsed_output
    if result is None:
        raise RuntimeError(f"Claude 응답 파싱 실패 (stop_reason={response.stop_reason})")
    return result.model_dump()


def self_evaluate_tone(client, payload: dict, headline: str) -> tuple[float, str]:
    prompt = (
        "다음 본문이 아래 썸네일 헤드라인과 톤·타겟이 일관되는지 평가하세요.\n"
        f"썸네일 헤드라인: {headline}\n\n"
        f"Card02: {payload['card02_title']} — {payload['card02_text']}\n"
        f"Card03: {payload['card03_title']} — {payload['card03_text']}\n"
        f"Card04: {payload['card04_title']} — {payload['card04_text']}\n"
        f"CTA: {payload['cta']}\n\n"
        "썸네일과 어투·타겟이 어긋나면 낮은 점수를 주고 comment에 구체적으로 지적하세요."
    )
    response = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=800,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
        output_format=ToneEval,
    )
    result = response.parsed_output
    if result is None:
        return 0.0, "자기 평가 파싱 실패"
    return result.tone_consistency, result.comment


def process_approved_thumbnails(auto: bool = False, client=None) -> list[dict]:
    """'썸네일 승인'이면서 본문이 아직 없는 행들을 처리한다."""
    import anthropic
    from verify_loop import run_self_eval_loop

    client = client or anthropic.Anthropic()
    sheet = SheetClient()
    sheet.ensure_headers()

    targets = [
        r
        for r in sheet.read_all()
        if r.get("썸네일 상태") == STATUS_THUMBNAIL_APPROVED and not r.get("본문 상태", "").strip()
    ]
    if not targets:
        print("본문 생성 대상('썸네일 승인'이면서 미처리)이 없습니다.")
        return []

    print(f"📄 본문 에이전트 시작 — {len(targets)}개 행 처리")
    processed = []
    for row in targets:
        headline = row.get("Card01 헤드라인", "").replace("\n", " / ")

        def _generate(feedback, row=row):
            return generate_body_for_row(client, row, feedback)

        def _validate(payload):
            ok, reason = _validate_body(payload)
            if ok:
                print("  ✅ 규칙 검증 통과")
            return ok, reason

        def _evaluate(payload, headline=headline):
            print("  🔍 Claude 톤 일관성 자기 평가 중...")
            return self_evaluate_tone(client, payload, headline)

        result = run_self_eval_loop(_generate, _evaluate, _validate)
        payload = result.payload
        status = STATUS_BODY_APPROVED if auto else STATUS_BODY_WAIT

        updates = {
            "Card02 섹션타이틀": payload.get("card02_title", ""),
            "Card02 인풋텍스트": payload.get("card02_text", ""),
            "Card03 섹션타이틀": payload.get("card03_title", ""),
            "Card03 인풋텍스트": payload.get("card03_text", ""),
            "Card04 섹션타이틀": payload.get("card04_title", ""),
            "Card04 인풋텍스트": payload.get("card04_text", ""),
            "Card05 CTA 유도문구": payload.get("cta", ""),
            "컨셉": payload.get("concept", ""),
            "기대반응": payload.get("expected_reaction", ""),
            "본문 상태": status,
        }
        sheet.update_row(row["_row"], updates)
        processed.append({**row, **updates})
        print(f"  [{row.get('앵글', '')}] 톤 일관성 {result.score}/10 (시도 {result.attempts}회)")

    print(f"✅ 저장 완료 — {len(processed)}행 본문 갱신됨")
    if auto:
        print("🤖 [자동 승인] --auto 모드로 본문 모두 '본문 승인' 처리됨")
    return processed


def main():
    parser = argparse.ArgumentParser(description="본문 에이전트")
    parser.add_argument("--auto", action="store_true")
    args = parser.parse_args()
    try:
        process_approved_thumbnails(auto=args.auto)
    except Exception as exc:
        print(f"❌ 본문 생성 실패: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
