"""Gemini API로 카드뉴스 '기획' 단계를 담당한다.

브랜드/서비스에 대한 짧은 브리프를 주면, Claude가 카피를 쓰기 전 단계인
'주제(Topic) + 타겟 페르소나' 조합을 여러 개 브레인스토밍하여
주제입력 시트에 자동으로 채워 넣는다.

    브리프 ─▶ Gemini(기획) ─▶ 주제·페르소나 N개 ─▶ 주제입력 시트
                                                      │
                                                      ▼
                                        (이후 generate 단계에서 Claude가 카피 생성)
"""

from __future__ import annotations

import json
from typing import List

from .config import Config
from .models import Topic, next_topic_ids

SYSTEM_PROMPT = """당신은 카드뉴스 마케팅 기획자입니다.
주어진 브랜드/서비스 브리프를 바탕으로, 카드뉴스 캠페인으로 다룰 만한
'주제(topic)'와 그 주제에 가장 반응할 '타겟 페르소나(persona)' 조합을
서로 뚜렷이 다른 관점으로 여러 개 기획합니다.

작성 규칙:
- 모든 결과는 한국어로 작성합니다.
- topic은 카드뉴스 한 세트의 소재가 될 만큼 구체적이어야 합니다.
  (예: "신규 회계 자동화 SaaS 출시" O, "회계" X — 너무 추상적)
- persona는 인구통계보다 상황·고민 중심으로 구체적으로 씁니다.
  (예: "매달 마감 때마다 수기 대사에 시달리는 중소기업 재무담당자")
- 각 조합은 서로 다른 타겟층·상황·니즈를 다뤄 겹치지 않게 합니다.
- 이미 존재하는 주제와 중복되거나 지나치게 유사한 주제는 피합니다.
- 반드시 아래 JSON 스키마로만 응답하고, 다른 텍스트는 출력하지 않습니다.

JSON 스키마:
{"topics": [{"topic": "string", "persona": "string", "rationale": "string(한 줄 기획 의도)"}]}
"""

USER_TEMPLATE = """브랜드/서비스 브리프:
{brief}

{existing_block}

위 브리프에 맞는 카드뉴스 주제·타겟 페르소나 조합을 {count}개 기획해 주세요."""


def _build_prompt(brief: str, count: int, existing_topics: list[Topic] | None) -> str:
    existing_block = ""
    if existing_topics:
        titles = "\n".join(f"- {t.topic}" for t in existing_topics[-30:])
        existing_block = f"이미 시트에 있는 기존 주제(중복 피하기):\n{titles}\n"
    return USER_TEMPLATE.format(brief=brief.strip(), existing_block=existing_block, count=count)


def generate_topics(
    config: Config,
    brief: str,
    count: int | None = None,
    existing_topics: list[Topic] | None = None,
) -> List[Topic]:
    """Gemini로 주제·페르소나 조합을 브레인스토밍하여 Topic 리스트를 반환.

    반환된 Topic은 아직 시트에 쓰이지 않은 상태이며, ID는 기존 주제 ID
    (T001, T002 ...) 다음 번호부터 자동 채번된다.
    """
    from google import genai
    from google.genai import types

    n = count or config.topics_per_plan
    client = genai.Client(api_key=config.require_gemini())

    prompt = _build_prompt(brief, n, existing_topics)
    response = client.models.generate_content(
        model=config.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )

    try:
        data = json.loads(response.text)
        raw_topics = data["topics"][:n]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError(
            f"Gemini 응답을 파싱하지 못했습니다: {exc}\n원본 응답: {(response.text or '')[:500]}"
        ) from exc

    existing_ids = [t.id for t in (existing_topics or [])]
    new_ids = next_topic_ids(existing_ids, len(raw_topics))

    return [
        Topic(id=new_ids[i], topic=item["topic"].strip(), persona=item["persona"].strip())
        for i, item in enumerate(raw_topics)
    ]
