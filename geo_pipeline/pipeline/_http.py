"""의존성 없는 최소 HTTP 헬퍼 (stdlib urllib) + robots.txt 확인.

RULE-11(외부 사이트 데이터 수집 기준) ①: 대상 사이트 robots 확인 후 시작.
글 페이지는 `allowed_by_robots()`를 통과한 경우에만 연다.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from typing import Any

DEFAULT_TIMEOUT = 15

_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def _request(url: str, params: dict | None, headers: dict | None, timeout: int) -> bytes:
    if params:
        qs = urllib.parse.urlencode(params, doseq=True)
        url = f"{url}{'&' if '?' in url else '?'}{qs}"
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (공식 API/공개 글)
        return resp.read()


def get_json(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    body = _request(url, params, headers, timeout)
    return json.loads(body.decode("utf-8"))


def get_text(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    body = _request(url, params, headers, timeout)
    return body.decode("utf-8", errors="replace")


def allowed_by_robots(url: str, user_agent: str) -> bool:
    """robots.txt가 이 URL을 허용하는지. robots를 못 읽으면 보수적으로 False."""
    parts = urllib.parse.urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            text = get_text(f"{origin}/robots.txt", headers={"User-Agent": user_agent})
            rp.parse(text.splitlines())
            _robots_cache[origin] = rp
        except Exception:
            _robots_cache[origin] = None
    rp = _robots_cache[origin]
    return bool(rp and rp.can_fetch(user_agent, url))


def polite_sleep(seconds: float) -> None:
    """요청 간 지연 (RULE-11: 빈도 최소)."""
    if seconds > 0:
        time.sleep(seconds)


def post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = DEFAULT_TIMEOUT) -> Any:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (Notion API)
        return json.loads(resp.read().decode("utf-8"))


def request_json(method: str, url: str, payload: dict | None = None, headers: dict | None = None,
                 timeout: int = DEFAULT_TIMEOUT) -> Any:
    """GET·POST·PATCH 공용 (노션 API)."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (Notion API)
        return json.loads(resp.read().decode("utf-8"))
