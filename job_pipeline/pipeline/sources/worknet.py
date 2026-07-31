"""워크넷(고용24) 채용정보 공식 API 어댑터.

- 제공: 고용노동부 워크넷 채용정보 오픈 API (work.go.kr / 공공데이터포털)
- 인증: authKey (WORKNET_AUTH_KEY)
- 응답: 기본 XML. callTp=L(목록) 으로 채용목록을 받고 wanted 항목을 파싱한다.
  (data.go.kr 신규 엔드포인트는 JSON도 지원하나, 여기선 호환성 위해 XML 파싱)

XML 필드는 기관에 따라 조금씩 다를 수 있어 방어적으로 접근한다. 실서비스 적용 시
포털에서 발급한 정확한 오퍼레이션/필드명으로 _ITEM_TAG, 매핑을 조정하면 된다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .. import _http
from ..models import JobPosting
from .base import BaseSource

ENDPOINT = "https://openapi.work.go.kr/opi/opi/opia/wantedApi.do"


class WorknetSource(BaseSource):
    key = "worknet"
    name = "워크넷"

    def fetch(self) -> list[dict]:
        params = {
            "authKey": self.config.worknet_auth_key,
            "callTp": "L",            # L=목록
            "returnType": "XML",
            "startPage": 1,
            "display": min(self.config.per_source_limit, 100),
            "keyword": " ".join(self.config.keywords[:3]),
        }
        headers = {"User-Agent": self.config.user_agent}
        try:
            text = _http.get_text(ENDPOINT, params=params, headers=headers)
        except Exception:
            return []
        return _parse_items(text)

    def normalize(self, raw: dict) -> JobPosting | None:
        company = raw.get("company", "").strip()
        title = raw.get("title", "").strip()
        if not company or not title:
            return None
        job = JobPosting(
            source=self.key,
            source_id=raw.get("wantedAuthNo") or raw.get("empSeqno") or "",
            company=company,
            title=title,
            url=raw.get("wantedInfoUrl", ""),
            level=raw.get("career", "경력무관") or "경력무관",
            location=raw.get("region", ""),
            employment_type=raw.get("holidayTpNm", ""),
            salary=raw.get("sal", "") or raw.get("salTpNm", ""),
            posted_at=_fmt_date(raw.get("regDt", "")),
            deadline=_fmt_date(raw.get("closeDt", "")),
            description=raw.get("jobsCd", ""),
            raw=raw,
        )
        return self.enrich(job)


# 목록 응답에서 개별 채용을 감싸는 태그(기관에 따라 wanted 또는 dhsOpenEmpInfo)
_ITEM_TAGS = ("wanted", "dhsOpenEmpInfo", "empInfo")


def _parse_items(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items: list[dict] = []
    for tag in _ITEM_TAGS:
        for el in root.iter(tag):
            items.append({child.tag: (child.text or "").strip() for child in el})
    return items


def _fmt_date(s: str) -> str:
    """YYYYMMDD → YYYY-MM-DD (그 외 형식은 앞 10자만)."""
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return s[:10]
