"""의존성 없는 최소 HTTP 헬퍼 (stdlib urllib).

job_pipeline/pipeline/_http.py 와 동일한 패턴. Meta Graph API는 REST/JSON이라
requests 없이도 표준 라이브러리만으로 충분하다.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_TIMEOUT = 15


class GraphAPIError(Exception):
    """Meta Graph API가 에러 응답(HTTP 4xx/5xx, error 객체)을 준 경우."""

    def __init__(self, message: str, status: int | None = None, body: dict | None = None):
        super().__init__(message)
        self.status = status
        self.body = body or {}


def _request(url: str, params: dict | None, headers: dict | None, timeout: int) -> bytes:
    if params:
        qs = urllib.parse.urlencode(params, doseq=True)
        url = f"{url}{'&' if '?' in url else '?'}{qs}"
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (신뢰된 Meta 도메인)
            return resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        msg = ((parsed.get("error") or {}).get("message")) or body[:200]
        raise GraphAPIError(msg, status=e.code, body=parsed) from e


def get_json(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    body = _request(url, params, headers, timeout)
    return json.loads(body.decode("utf-8"))


def polite_sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)
