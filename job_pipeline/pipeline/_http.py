"""의존성 없는 최소 HTTP 헬퍼 (stdlib urllib).

requests 미설치 환경에서도 API 소스가 동작하도록 표준 라이브러리만 사용한다.
크롤러/공식 API 모두 여기를 거쳐 User-Agent·타임아웃을 일관되게 적용한다.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_TIMEOUT = 15


def _request(url: str, params: dict | None, headers: dict | None, timeout: int) -> bytes:
    if params:
        qs = urllib.parse.urlencode(params, doseq=True)
        url = f"{url}{'&' if '?' in url else '?'}{qs}"
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (신뢰된 채용 API/도메인)
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
    return body.decode("utf-8")


def polite_sleep(seconds: float) -> None:
    """크롤러 rate-limit 매너용 지연."""
    if seconds > 0:
        time.sleep(seconds)
