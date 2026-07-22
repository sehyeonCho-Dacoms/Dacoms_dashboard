"""Claude API로 P.D.A. 프레임워크 기반 카드뉴스 카피(5앵글)를 생성한다.

P.D.A. 프레임워크 (본 파이프라인 정의):
    P — Problem : 타겟 페르소나가 겪는 문제·불편·결핍을 짚는다.
    D — Desire  : 문제가 해결된 이상적 상태, 얻게 될 이득/변화를 그린다.
    A — Action  : 그 상태에 도달하기 위한 구체적 다음 행동을 제시한다.

하나의 주제에 대해 서로 '앵글(설득 관점)'이 다른 5가지 카피를 생성한다.
각 카피는 표지 후킹 문구 + P/D/A 본문 + CTA + 이미지 프롬프트를 포함한다.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from .config import Config
from .models import CopyAngle, Topic

SYSTEM_PROMPT = """당신은 B2B/B2C 브랜드의 카드뉴스 카피라이터입니다.
주어진 '주제'와 '타겟 페르소나'를 바탕으로 P.D.A. 프레임워크에 따라
서로 다른 설득 앵글의 카드뉴스 카피를 작성합니다.

P.D.A. 프레임워크:
- P (Problem): 페르소나가 실제로 겪는 문제·불편·결핍을 구체적으로 짚습니다.
- D (Desire): 문제가 해결된 이상적 모습, 얻게 될 이득과 변화를 감각적으로 그립니다.
- A (Action): 그 변화를 위해 지금 할 수 있는 명확한 다음 행동을 제시합니다.

작성 규칙:
- 모든 문구는 한국어로, 카드뉴스 톤(간결·임팩트)으로 작성합니다.
- 후킹(hook)은 표지에 들어갈 한 문장으로, 스크롤을 멈추게 하는 강한 문구여야 합니다.
- 5개 앵글은 관점이 서로 뚜렷이 달라야 합니다.
  (예: 공감형, 정보/데이터형, 위기감·손실회피형, 혜택·이득강조형, 스토리텔링형)
- image_prompt는 표지 배경 이미지를 만들기 위한 영어 프롬프트로,
  텍스트가 없는(no text) 브랜드 무드의 추상/사진 이미지를 묘사합니다.
"""

USER_TEMPLATE = """주제: {topic}
타겟 페르소나: {persona}

위 주제와 페르소나에 맞춰 서로 다른 설득 앵글의 카드뉴스 카피 {n}개를 작성해 주세요."""


class Angle(BaseModel):
    angle_name: str = Field(description="앵글명 (예: 공감형, 정보형, 위기감형)")
    angle_description: str = Field(description="이 앵글의 설득 관점 한 줄 설명")
    hook: str = Field(description="표지 후킹 문구 (한 문장)")
    problem: str = Field(description="P — 문제 제기 본문")
    desire: str = Field(description="D — 욕망/기대 본문")
    action: str = Field(description="A — 행동 유도 본문")
    cta: str = Field(description="마지막 카드의 CTA 문구 (짧게)")
    image_prompt: str = Field(description="표지 배경 이미지 생성용 영어 프롬프트 (no text)")


class AngleSet(BaseModel):
    angles: List[Angle]


def generate_angles(config: Config, topic: Topic) -> List[CopyAngle]:
    """Claude로 하나의 주제에 대한 P.D.A. 카피 앵글들을 생성한다."""
    import anthropic

    client = anthropic.Anthropic(api_key=config.require_anthropic())
    n = config.angles_per_topic

    response = client.messages.parse(
        model=config.claude_model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": USER_TEMPLATE.format(
                    topic=topic.topic, persona=topic.persona, n=n
                ),
            }
        ],
        output_format=AngleSet,
    )

    result = response.parsed_output
    if result is None:
        raise RuntimeError(
            f"Claude 응답 파싱 실패 (stop_reason={response.stop_reason}). 주제: {topic.topic}"
        )

    angles = result.angles[:n]
    return [
        CopyAngle(
            topic_id=topic.id,
            topic=topic.topic,
            persona=topic.persona,
            angle_name=a.angle_name,
            angle_description=a.angle_description,
            hook=a.hook,
            problem=a.problem,
            desire=a.desire,
            action=a.action,
            cta=a.cta,
            image_prompt=a.image_prompt,
        )
        for a in angles
    ]
