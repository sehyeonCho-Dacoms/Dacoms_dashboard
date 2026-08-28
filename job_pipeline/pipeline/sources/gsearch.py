"""구글 프로그래머블 검색(Custom Search JSON API)으로 사람인·잡코리아 등
공식 API가 없는 채용 사이트의 공고를 "검색 결과" 형태로 찾는 소스.

⚠️ 무엇을 하고, 무엇을 하지 않는지 (반드시 읽을 것)
    - 사람인/잡코리아 서버에 직접 접속해 페이지를 긁지 않는다. 구글이 이미
      공개적으로 색인해둔 제목·링크·짧은 스니펫만 구글 "공식" API로 조회한다.
      (google.com/search HTML을 직접 크롤링하는 것은 구글 ToS 위반이자 즉시
      차단 대상이므로 절대 하지 않는다 — 반드시 Custom Search JSON API만 사용)
    - 공고 "본문"은 가져오지 않는다. 제목/스니펫 텍스트로 1차 스코어링만 하고,
      실제 내용 확인·헤드헌팅 접근은 사람이 원문 링크에서 확인해야 한다.
    - 스니펫만으로는 회사명을 신뢰성 있게 파싱하지 못하는 경우가 많다.
      추출에 확신이 없으면 `verified_company=False`로 표시한다 — 이 값이
      False인 공고는 scoring.build_leads()의 회사 단위 집계에서 자동
      제외되고, export의 "오늘의 액션"에서도 "지금 업로드"가 아니라
      "원문 확인 후 업로드"로 낮춰 표시된다(export.py 참고).

발급 방법:
    1) https://programmablesearchengine.google.com 에서 검색엔진 생성,
       "전체 웹 검색"으로 설정 → 검색엔진 ID(cx) 확인
    2) https://console.cloud.google.com 에서 Custom Search API 활성화 →
       API 키 발급
    무료 하루 100건, 초과분은 1,000건당 $5.
"""

from __future__ import annotations

import hashlib
import re

from .. import _http
from ..models import JobPosting
from .base import BaseSource

ENDPOINT = "https://www.googleapis.com/customsearch/v1"

# 채용공고 상세 페이지로 보이는 URL 힌트 (사이트 메인/블로그/카테고리 페이지 등 노이즈 제거)
_JOB_URL_HINTS = ("recruit", "/jobs/", "rec_idx", "gi_read", "gno=", "jv_")

# 제목 끝의 사이트명 접미사 제거용
_SITE_SUFFIX_RE = re.compile(r"\s*[|\-:]\s*(사람인|잡코리아|saramin|jobkorea)\s*$", re.I)

# 회사명 후보 판별에 쓰는 "직무/공고" 신호 키워드
_ROLE_HINTS = ("채용", "모집", "구인", "담당자", "매니저", "인턴", "신입", "경력")

_SITE_SLUG = {"saramin": "saramin", "jobkorea": "jobkorea"}


class GoogleSearchSource(BaseSource):
    key = "gsearch"
    name = "구글 검색(사람인·잡코리아)"

    def fetch(self) -> list[dict]:
        api_key = self.config.google_cse_api_key
        cx = self.config.google_cse_id
        headers = {"User-Agent": self.config.user_agent}
        sites = self.config.google_cse_sites or ["saramin.co.kr", "jobkorea.co.kr"]

        rows: list[dict] = []
        queries_used = 0
        for site in sites:
            for kw in self.config.keywords:
                for page in range(max(1, self.config.google_cse_pages)):
                    if queries_used >= self.config.google_cse_daily_cap:
                        return rows[: self.config.per_source_limit]
                    params = {
                        "key": api_key,
                        "cx": cx,
                        "q": f"site:{site} {kw} 채용",
                        "num": min(10, self.config.per_source_limit),
                        "hl": "ko",
                        "gl": "kr",
                    }
                    start = page * 10 + 1
                    if start > 1:
                        params["start"] = start
                    queries_used += 1
                    try:
                        data = _http.get_json(ENDPOINT, params=params, headers=headers)
                    except Exception:
                        continue
                    for item in data.get("items") or []:
                        item = dict(item)
                        item["_site"] = site
                        rows.append(item)
                    _http.polite_sleep(self.config.request_delay_sec)
                    if len(rows) >= self.config.per_source_limit:
                        return rows[: self.config.per_source_limit]
        return rows[: self.config.per_source_limit]

    def normalize(self, raw: dict) -> JobPosting | None:
        link = raw.get("link") or ""
        title_raw = (raw.get("title") or "").strip()
        if not link or not title_raw or not _looks_like_posting(link):
            return None
        title = _clean_title(title_raw)
        if not title:
            return None

        snippet = (raw.get("snippet") or "").strip()
        company, confident = _guess_company(title_raw)
        slug = _slug_for_site(raw.get("_site") or link)

        job = JobPosting(
            source=f"gsearch_{slug}",
            source_id=_hash_id(link),
            company=company or "확인필요(원문 참조)",
            title=title,
            url=link,
            description=snippet,
            verified_company=confident,
            raw=raw,
        )
        return self.enrich(job)


# --------------------------------------------------------------------------- #
def _looks_like_posting(link: str) -> bool:
    l = (link or "").lower()
    return any(h in l for h in _JOB_URL_HINTS)


def _clean_title(title: str) -> str:
    return _SITE_SUFFIX_RE.sub("", title or "").strip()


def _guess_company(raw_title: str) -> tuple[str | None, bool]:
    """제목에서 회사명을 보수적으로 추정한다. 확신 없으면 (None, False).

    잡코리아/사람인 검색결과 제목은 보통 "회사명 - 공고제목" 또는
    "공고제목 | 회사명" 형태다. 구분자 양쪽 중 '채용/모집' 등 직무 신호가
    없는 쪽 + 길이가 짧은(20자 이하) 쪽을 회사명으로 추정한다.
    """
    t = _clean_title(raw_title)
    for sep in (" - ", " | ", " :: ", " : "):
        if sep not in t:
            continue
        parts = [p.strip() for p in t.split(sep) if p.strip()]
        if len(parts) != 2:
            continue
        a, b = parts
        a_role = any(k in a for k in _ROLE_HINTS)
        b_role = any(k in b for k in _ROLE_HINTS)
        if a_role and not b_role and 1 < len(b) <= 20:
            return b, True
        if b_role and not a_role and 1 < len(a) <= 20:
            return a, True
    return None, False


def _slug_for_site(site: str) -> str:
    s = (site or "").lower()
    for needle, slug in _SITE_SLUG.items():
        if needle in s:
            return slug
    return re.sub(r"\W+", "_", s).strip("_") or "web"


def _hash_id(link: str) -> str:
    return hashlib.sha1(link.encode("utf-8")).hexdigest()[:12]
