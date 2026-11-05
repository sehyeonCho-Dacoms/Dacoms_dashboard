"""실패·주의 알림 (D-030, 11/5 세현 결정) — 슬랙은 '어디서 끊겼는지 확인'용이다.

각 노드는 알릴 일을 로그에 한 줄로 남긴다.
  ❌ ...                          → 실패 (워크플로도 빨간색으로 끝남)
  🔔 [노드] 빈칸 유형 · 조치: ...  → 자동으로 고쳤거나 사람이 볼 일 (워크플로는 초록)
워크플로 마지막 단계가 `python -m pipeline.cli notify --log g3_log.txt` 로 이 줄들만 모아 슬랙에 보낸다.

Secrets(선택): SLACK_WEBHOOK_URL — 없으면 아무것도 보내지 않고 로그에 '건너뜀'만 찍는다
(세현 님이 채널·웹훅을 만들기 전에도 워크플로가 깨지지 않게).
"""

from __future__ import annotations

import os

from . import _http

MARKS = ("❌", "🔔")


def alert(node: str, gap: str, action: str) -> str:
    """로그에 남길 알림 한 줄. 메시지 형식은 D-030: 노드 ID · 빈칸 유형 · 조치."""
    return f"🔔 [{node}] {gap} · 조치: {action}"


def pick_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith(MARKS)]


def message(title: str, lines: list[str], run_url: str = "") -> str:
    body = "\n".join(f"• {ln}" for ln in lines)
    return f"*{title}*\n{body}" + (f"\n<{run_url}|실행 기록 보기>" if run_url else "")


def send(title: str, log_text: str, run_url: str = "") -> str:
    lines = pick_lines(log_text)
    if not lines:
        return "   알림 없음"
    hook = os.getenv("SLACK_WEBHOOK_URL")
    if not hook:
        return f"   알림 {len(lines)}건 · SLACK_WEBHOOK_URL 이 없어 슬랙 전송은 건너뜀"
    _http.post_raw(hook, {"text": message(title, lines, run_url)})
    return f"   슬랙 알림 {len(lines)}건 보냄"
