"""헤드라인·페르소나 → DALL-E 배경 이미지 프롬프트 변환 (Claude Haiku 2단계).

image_agent.py와 pipeline.py에서 공통으로 사용한다.
    1단계 — 헤드라인(한국어) → 구체적 시각 장면 묘사(영어)
    2단계 — 페르소나 → 스타일/색감/분위기 묘사(영어)
"""

from __future__ import annotations

SCENE_PROMPT = """다음 한국어 카드뉴스 헤드라인을 이미지 생성 AI가 이해할 수 있는
구체적인 영어 시각 장면 묘사로 변환하세요. 설명 없이 장면 묘사 문장만 출력하세요.

헤드라인: {headline}

예시)
"마케터 필수 AI 툴 3가지" → "Three glowing keycaps with AI symbols arranged on a sleek dark keyboard"
"""

STYLE_PROMPT = """다음 타겟 페르소나에 어울리는 이미지 스타일·색감·분위기를
영어로 묘사하세요. 설명 없이 스타일 묘사 문장만 출력하세요.

페르소나: {persona}

예시)
"2030 주니어 마케터" → "Modern, high-tech aesthetic with cyan and purple neon light accents on a dark background"
"""


def _ask_haiku(client, prompt: str) -> str:
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            return block.text.strip()
    return ""


def build_dalle_prompt(client, headline: str, persona: str) -> str:
    """헤드라인+페르소나를 조합해 최종 DALL-E 프롬프트(영어)를 생성한다."""
    scene = _ask_haiku(client, SCENE_PROMPT.format(headline=headline))
    style = _ask_haiku(client, STYLE_PROMPT.format(persona=persona))
    return (
        f"{scene}. {style}. High quality background image for a social media card, "
        f"no text, no letters, no watermark."
    )
