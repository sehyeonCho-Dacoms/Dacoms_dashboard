"""사람인 채용정보 공식 Open API 어댑터.

- 문서: https://oapi.saramin.co.kr/ (사람인 인재풀/채용 오픈 API)
- 인증: 발급받은 access-key 를 쿼리스트링으로 전달 (SARAMIN_ACCESS_KEY)
- 응답: JSON. jobs.job[] 배열, 각 항목에 company/position/… 중첩 구조.

키가 없으면 config.enabled_source_keys()에서 자동 제외되므로 여기선 키 존재를
가정한다. 여러 키워드를 순회하며 수집하고, per_source_limit로 총량을 제한한다.
"""

from __future__ import annotations

from .. import _http
from ..models import JobPosting
from .base import BaseSource

ENDPOINT = "https://oapi.saramin.co.kr/job-search"


class SaraminSource(BaseSource):
    key = "saramin"
    name = "사람인"

    def fetch(self) -> list[dict]:
        access_key = self.config.saramin_access_key
        collected: list[dict] = []
        per_kw = max(1, self.config.per_source_limit // max(1, len(self.config.keywords)))
        for kw in self.config.keywords:
            params = {
                "access-key": access_key,
                "keywords": kw,
                "count": min(per_kw, 110),   # 사람인 최대 110
                "sort": "pd",                # 등록일순
                "fields": "posting-date,expiration-date,count",
            }
            headers = {"Accept": "application/json", "User-Agent": self.config.user_agent}
            try:
                data = _http.get_json(ENDPOINT, params=params, headers=headers)
            except Exception:
                continue
            jobs = (data.get("jobs") or {}).get("job") or []
            collected.extend(jobs)
            _http.polite_sleep(self.config.request_delay_sec)
            if len(collected) >= self.config.per_source_limit:
                break
        return collected[: self.config.per_source_limit]

    def normalize(self, raw: dict) -> JobPosting | None:
        pos = raw.get("position") or {}
        company = ((raw.get("company") or {}).get("detail") or {}).get("name", "")
        title = pos.get("title", "")
        if not company or not title:
            return None

        industry = _name(pos.get("industry"))
        job_cat = _name(pos.get("job-code")) or _name(pos.get("job-mid-code"))
        exp = _name(pos.get("experience-level"))
        loc = _name(pos.get("location"))

        job = JobPosting(
            source=self.key,
            source_id=str(raw.get("id", "")),
            company=company,
            title=title,
            url=raw.get("url", ""),
            role=_map_role(job_cat, title),
            level=exp or "경력무관",
            location=loc,
            employment_type=_name(pos.get("job-type")),
            salary=_name(raw.get("salary")),
            posted_at=(raw.get("posting-date") or "")[:10],
            deadline=(raw.get("expiration-date") or "")[:10],
            description=f"{industry} {job_cat}".strip(),
            raw=raw,
        )
        return self.enrich(job)


def _name(node) -> str:
    """{'code':.., 'name':..} 또는 문자열에서 name을 안전 추출."""
    if isinstance(node, dict):
        return str(node.get("name", "")).strip()
    return str(node or "").strip()


def _map_role(job_cat: str, title: str) -> str:
    from ..taxonomy import normalize_role

    return normalize_role(job_cat, title)
