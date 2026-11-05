"""슬랙 알림 (D-046·D-047, 11/5 세현 님 결정) — 슬랙은 '어디서 끊겼는지 확인'용이다.

공용 채널 #geo-체인-알림 하나에 앞단(세현 Actions)·뒷단(웅서 작업키트)이 같이 보낸다.
기호는 웅서 님 설계 3종으로 통일:
  ⛔ 실패      → 바로 알림. 당일 대응 (워크플로도 빨간색)
  ⏸ 멈춤·주의  → 사람이 볼 일. 다음 날 오전까지 대응 (워크플로는 초록)
  ✅ 하루 요약  → 문제가 없어도 하루 1번. 안 오면 그 자체가 이상 신호

로그 안에서는 실패 줄을 계속 ❌ 로 쓴다(워크플로의 `grep -q "❌"` 실패 판정과 다른 모듈이 그대로 쓰므로).
슬랙으로 보낼 때만 ❌ 를 ⛔ 로 바꿔 적는다.

워크플로 마지막 단계가 `python -m pipeline.cli notify --log g8_log.txt [--daily]` 로 이 줄들만 모아 보낸다.
Secrets(선택): SLACK_WEBHOOK_URL — 없으면 아무것도 보내지 않고 로그에 '건너뜀'만 찍는다.
"""

from __future__ import annotations

import os

from . import _http

FAIL_LOG = "❌"   # 로그 속 실패 표시 (워크플로 실패 판정)
STOP, HOLD, OK = "⛔", "⏸", "✅"
MARKS = (FAIL_LOG, STOP, HOLD)

# 노드 주인 (D-047): 앞단 G0~G3·G8 = 세현, 뒷단 G4~G7·G8-d·G9·G10 = 웅서
BACK_NODES = ("G4", "G5", "G6", "G7", "G8-d", "G9", "G10")


def owner_of(node: str) -> str:
    return "웅서" if any(n in node for n in BACK_NODES) else "세현"


def alert(node: str, gap: str, action: str, owner: str | None = None) -> str:
    """로그에 남길 멈춤·주의 한 줄. 형식(D-046): 노드 · 빈칸 유형 · 사람이 할 일 · 담당."""
    return f"{HOLD} [{node}] {gap} · 조치: {action} · 담당: {owner or owner_of(node)}"


def pick_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith(MARKS)]


def _for_slack(line: str) -> str:
    return STOP + line[len(FAIL_LOG):] if line.startswith(FAIL_LOG) else line


def message(title: str, lines: list[str], run_url: str = "") -> str:
    body = "\n".join(f"• {_for_slack(ln)}" for ln in lines)
    return f"*{title}*\n{body}" + (f"\n<{run_url}|실행 기록 보기>" if run_url else "")


def daily_ok(title: str, summary: list[str], run_url: str = "") -> str:
    body = "\n".join(f"• {s.strip()}" for s in summary if s.strip())
    head = f"{OK} *{title}* 문제 없음"
    return head + (f"\n{body}" if body else "") + (f"\n<{run_url}|실행 기록 보기>" if run_url else "")


def send(title: str, log_text: str, run_url: str = "", daily: bool = False,
         summary: list[str] | None = None) -> str:
    """⛔·⏸ 줄이 있으면 그것만 보낸다. 없으면 daily=True 일 때만 ✅ 하루 요약을 보낸다."""
    lines = pick_lines(log_text)
    if not lines and not daily:
        return "   알림 없음"
    text = message(title, lines, run_url) if lines else daily_ok(title, summary or [], run_url)
    what = f"알림 {len(lines)}건" if lines else "✅ 하루 요약"
    hook = os.getenv("SLACK_WEBHOOK_URL")
    if not hook:
        return f"   {what} · SLACK_WEBHOOK_URL 이 없어 슬랙 전송은 건너뜀"
    _http.post_raw(hook, {"text": text})
    return f"   슬랙 {what} 보냄"
