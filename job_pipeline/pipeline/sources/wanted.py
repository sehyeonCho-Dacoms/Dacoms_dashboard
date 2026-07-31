"""원티드(wanted.co.kr) 크롤러 어댑터 — 공식 오픈 API 부재로 내부 JSON 사용.

⚠️  법적 주의 (반드시 읽을 것)
    원티드는 공개 오픈 API를 제공하지 않는다. 이 어댑터는 웹에서 쓰이는 내부
    JSON 엔드포인트를 호출하므로, 사용 전 반드시:
      1) robots.txt 및 서비스 이용약관(ToS) 확인
      2) 개인정보·저작권 문제 없는 범위(회사/공고 메타데이터)만 수집
      3) 제휴/데이터 이용 계약이 가능하면 그 경로를 우선
    를 검토하고, 동의한 경우에만 WANTED_CRAWLER_ENABLED=true 로 켠다.
    (기본은 비활성 — config에서 자동 제외된다.)

    엔드포인트/파라미터는 예고 없이 바뀔 수 있으므로 실패해도 파이프라인 전체가
    멈추지 않도록 방어적으로 처리한다.
"""

from __future__ import annotations

from .. import _http
from ..models import JobPosting
from .base import BaseSource

# 스포츠 관련 태그/카테고리를 keyword 질의로 사용
ENDPOINT = "https://www.wanted.co.kr/api/v4/jobs"


class WantedSource(BaseSource):
    key = "wanted"
    name = "원티드"

    def fetch(self) -> list[dict]:
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "application/json",
        }
        collected: list[dict] = []
        per_kw = max(1, self.config.per_source_limit // max(1, len(self.config.keywords)))
        for kw in self.config.keywords:
            params = {"query": kw, "country": "kr", "job_sort": "job.latest_order",
                      "limit": min(per_kw, 100), "offset": 0}
            try:
                data = _http.get_json(ENDPOINT, params=params, headers=headers)
            except Exception:
                continue
            collected.extend(data.get("data") or [])
            _http.polite_sleep(self.config.request_delay_sec)
            if len(collected) >= self.config.per_source_limit:
                break
        return collected[: self.config.per_source_limit]

    def normalize(self, raw: dict) -> JobPosting | None:
        company = ((raw.get("company") or {}).get("name")) or raw.get("company_name", "")
        title = raw.get("position") or raw.get("title", "")
        if not company or not title:
            return None
        job_id = str(raw.get("id", ""))
        job = JobPosting(
            source=self.key,
            source_id=job_id,
            company=str(company).strip(),
            title=str(title).strip(),
            url=f"https://www.wanted.co.kr/wd/{job_id}" if job_id else "",
            location=(raw.get("address") or {}).get("location", "") if isinstance(raw.get("address"), dict) else "",
            description=raw.get("category_tag", "") or "",
            posted_at=(raw.get("confirm_time") or "")[:10],
            raw=raw,
        )
        return self.enrich(job)
