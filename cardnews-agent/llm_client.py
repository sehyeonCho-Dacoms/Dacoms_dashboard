"""Gemini API 공용 클라이언트 — Claude 크레딧 없이 카피 생성/자기평가를 진행하기 위한 대체 엔진.

thumbnail_agent.py, body_agent.py, prompt_builder.py가 공유한다.
JSON 모드(response_mime_type='application/json')로 호출하고, 각 호출부에서
프롬프트에 명시한 스키마에 맞춰 dict를 반환한다 (Gemini는 Claude의
output_format=PydanticModel 같은 네이티브 파싱 기능이 없어 prompt+JSON모드로
받은 뒤 호출부에서 Pydantic 모델로 검증한다).

무료 티어는 분당 요청 수가 매우 낮아(모델당 5회) 429(RESOURCE_EXHAUSTED)가
자주 발생한다. 이를 감지해 API가 알려주는 retryDelay만큼 기다렸다가
자동 재시도한다.
"""

from __future__ import annotations

import json
import os
import re
import time

from dotenv import load_dotenv

load_dotenv()

_DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
_MAX_RETRIES = 6
_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


def _extract_retry_delay(exc: Exception, default: float = 15.0) -> float:
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", str(exc))
    if m:
        return float(m.group(1)) + 1.0  # 여유 1초
    return default


def _is_rate_limit_error(exc: Exception) -> bool:
    s = str(exc)
    return "429" in s or "RESOURCE_EXHAUSTED" in s or "rate limit" in s.lower()


def _call_with_retry(fn, *args, **kwargs):
    last_exc = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            if not _is_rate_limit_error(exc):
                raise
            last_exc = exc
            delay = _extract_retry_delay(exc)
            print(f"  ⏳ Gemini 속도 제한(429) — {delay:.0f}초 대기 후 재시도 ({attempt}/{_MAX_RETRIES})...")
            time.sleep(delay)
    raise last_exc


def generate_json(system_instruction: str, user_prompt: str, model: str | None = None) -> dict:
    """JSON 모드로 호출하고 파싱된 dict를 반환. 프롬프트에 JSON 스키마를 명시해야 한다."""
    from google.genai import types

    def _do():
        client = _get_client()
        response = client.models.generate_content(
            model=model or _DEFAULT_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
            ),
        )
        text = response.text
        if not text:
            raise RuntimeError("Gemini가 빈 응답을 반환했습니다.")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Gemini JSON 파싱 실패: {exc}\n원본: {text[:500]}") from exc

    return _call_with_retry(_do)


def generate_text(prompt: str, model: str | None = None) -> str:
    """일반 텍스트 응답을 반환 (DALL-E 프롬프트 변환 등 짧은 변환 작업용)."""

    def _do():
        client = _get_client()
        response = client.models.generate_content(model=model or _DEFAULT_MODEL, contents=prompt)
        return (response.text or "").strip()

    return _call_with_retry(_do)
