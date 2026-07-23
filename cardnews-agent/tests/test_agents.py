"""네트워크·API 키 없이 실행 가능한 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from verify_loop import run_self_eval_loop, validate_headline_rules
from sheet_client import HEADERS, _extract_sheet_id
from body_agent import _validate_body
from thumbnail_agent import _slugify_persona


# ---------------------------------------------------------------------- #
# validate_headline_rules
# ---------------------------------------------------------------------- #
def test_validate_headline_rules_passes():
    ok, reason = validate_headline_rules(["야근의 절반이요", "엑셀 탓이었어요", "이제는 자동화로"])
    assert ok, reason


def test_validate_headline_rules_wrong_line_count():
    ok, reason = validate_headline_rules(["한 줄만 있음"])
    assert not ok
    assert "3줄" in reason


def test_validate_headline_rules_too_short():
    ok, reason = validate_headline_rules(["짧음", "엑셀 탓이었죠", "이제는 자동화로"])
    assert not ok
    assert "7~12자" in reason or "자입니다" in reason


def test_validate_headline_rules_too_long():
    ok, reason = validate_headline_rules(
        ["이것은 너무너무 긴 첫번째 줄입니다 확실히", "엑셀 탓이었죠", "이제는 자동화로"]
    )
    assert not ok


def test_validate_headline_rules_ignores_spaces_in_count():
    # 공백 제외 7~12자 — 공백 포함하면 길어도 공백 제외 시 규칙 통과해야 함
    ok, reason = validate_headline_rules(["야 근 의 절 반 이 요", "엑셀 탓이었어요", "이제는 자동화로"])
    assert ok, reason


# ---------------------------------------------------------------------- #
# run_self_eval_loop
# ---------------------------------------------------------------------- #
def test_verify_loop_passes_on_first_try():
    calls = {"generate": 0, "evaluate": 0}

    def generate(feedback):
        calls["generate"] += 1
        return {"text": "ok"}

    def evaluate(payload):
        calls["evaluate"] += 1
        return 8.0, "통과"

    result = run_self_eval_loop(generate, evaluate)
    assert result.passed
    assert result.attempts == 1
    assert calls["generate"] == 1


def test_verify_loop_retries_until_pass_score():
    scores = iter([4.0, 6.0, 9.0])

    def generate(feedback):
        return {"attempt": feedback}

    def evaluate(payload):
        return next(scores), "재작성 필요" if payload else "통과"

    result = run_self_eval_loop(generate, evaluate)
    assert result.passed
    assert result.attempts == 3
    assert result.score == 9.0


def test_verify_loop_exhausts_attempts_returns_best():
    scores = iter([3.0, 5.0, 4.0])

    def generate(feedback):
        return {"x": 1}

    def evaluate(payload):
        return next(scores), "미흡"

    result = run_self_eval_loop(generate, evaluate, max_attempts=3)
    assert not result.passed
    assert result.attempts == 3
    assert result.score == 5.0  # 세 시도 중 최고점


def test_verify_loop_validate_rejects_before_evaluate():
    calls = {"evaluate": 0}

    def generate(feedback):
        return {"lines": ["짧음"] if feedback is None else ["충분히 길게 만든 문장 입니다"]}

    def evaluate(payload):
        calls["evaluate"] += 1
        return 9.0, "통과"

    def validate(payload):
        ok = len(payload["lines"][0]) > 5
        return ok, "너무 짧음"

    result = run_self_eval_loop(generate, evaluate, validate=validate)
    assert result.passed
    assert calls["evaluate"] == 1  # 첫 시도는 validate에서 걸러져 evaluate 호출 안 됨


# ---------------------------------------------------------------------- #
# sheet_client
# ---------------------------------------------------------------------- #
def test_headers_has_22_columns():
    assert len(HEADERS) == 22
    assert HEADERS[0] == "날짜"
    assert HEADERS[-1] == "PNG 폴더"
    assert HEADERS[10] == "썸네일 상태"  # K열 (0-based index 10)
    assert HEADERS[20] == "본문 상태"    # U열


def test_extract_sheet_id():
    url = "https://docs.google.com/spreadsheets/d/1ypNIPVZtBLOWqxZzKlFQTPoQKKHt44dgWD63q07tNhw/edit"
    assert _extract_sheet_id(url) == "1ypNIPVZtBLOWqxZzKlFQTPoQKKHt44dgWD63q07tNhw"


# ---------------------------------------------------------------------- #
# body_agent
# ---------------------------------------------------------------------- #
def test_validate_body_ok():
    payload = {
        "card02_title": "제목1", "card02_text": "충분히 긴 본문 텍스트입니다.",
        "card03_title": "제목2", "card03_text": "충분히 긴 본문 텍스트입니다.",
        "card04_title": "제목3", "card04_text": "충분히 긴 본문 텍스트입니다.",
        "cta": "지금 시작하세요",
    }
    ok, reason = _validate_body(payload)
    assert ok, reason


def test_validate_body_missing_field():
    payload = {
        "card02_title": "", "card02_text": "충분히 긴 본문 텍스트입니다.",
        "card03_title": "제목2", "card03_text": "충분히 긴 본문 텍스트입니다.",
        "card04_title": "제목3", "card04_text": "충분히 긴 본문 텍스트입니다.",
        "cta": "지금 시작하세요",
    }
    ok, reason = _validate_body(payload)
    assert not ok


def test_validate_body_too_short_text():
    payload = {
        "card02_title": "제목1", "card02_text": "짧음",
        "card03_title": "제목2", "card03_text": "충분히 긴 본문 텍스트입니다.",
        "card04_title": "제목3", "card04_text": "충분히 긴 본문 텍스트입니다.",
        "cta": "지금 시작하세요",
    }
    ok, reason = _validate_body(payload)
    assert not ok


# ---------------------------------------------------------------------- #
# thumbnail_agent
# ---------------------------------------------------------------------- #
def test_slugify_persona():
    assert _slugify_persona("3년차 마케터!!") == "3년차마케터"


def test_slugify_persona_truncates():
    long_persona = "매우매우매우매우매우매우매우긴페르소나이름입니다"
    assert len(_slugify_persona(long_persona, maxlen=12)) <= 12
