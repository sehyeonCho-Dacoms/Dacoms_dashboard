"""대한체육회(sports.or.kr) 채용공고 게시판 크롤러.

대상: https://sports.or.kr/sports/bbs/BMSR00024/list.do?menuNo=200027
표준 eGovFrame 게시판(bbs/<bbsId>/list.do → view.do) 구조를 파싱한다.

- 공개 채용공고 게시판이라 별도 인증키가 필요 없다(그래서 자격증명 게이트 없음).
- 공공 정보이지만 robots.txt / 이용 정책을 준수하고, 메타데이터+원문 링크만
  수집한다. request_delay_sec 로 요청 간 간격을 둔다(과도 요청 금지).
- 목록/상세 URL의 bbsId·menuNo 는 설정된 리스트 URL에서 자동 추출하므로,
  같은 사이트의 다른 eGov 게시판에도 KSOC_LIST_URL 만 바꿔 재사용할 수 있다.

⚠️ 사이트 마크업이 표준과 다르면 _parse_list 의 선택 규칙만 조정하면 된다.
"""

from __future__ import annotations

import re
import urllib.parse
from html import unescape

from .. import _http
from ..models import JobPosting
from .base import BaseSource

DEFAULT_LIST_URL = "https://sports.or.kr/sports/bbs/BMSR00024/list.do?menuNo=200027"

# 상세 링크에서 게시글 ID를 담는 대표 파라미터명들(eGov 변형 대응)
_ID_PARAMS = ("nttId", "nttSn", "dataSid", "dataSn", "bbscttSn", "boardSeq", "idx", "seq")


class KsocSource(BaseSource):
    key = "ksoc"
    name = "대한체육회"

    def __init__(self, config) -> None:
        super().__init__(config)
        self.list_url = getattr(config, "ksoc_list_url", None) or DEFAULT_LIST_URL
        self.pages = max(1, int(getattr(config, "ksoc_pages", 2)))
        parts = urllib.parse.urlparse(self.list_url)
        self.base = f"{parts.scheme}://{parts.netloc}"
        self.dir = parts.path.rsplit("/", 1)[0]                 # /sports/bbs/BMSR00024
        q = urllib.parse.parse_qs(parts.query)
        self.menu_no = q.get("menuNo", [""])[0]
        m = re.search(r"/bbs/([^/]+)/", parts.path)
        self.bbs_id = m.group(1) if m else ""

    # ── 수집 ────────────────────────────────────────────────
    def fetch(self) -> list[dict]:
        headers = {"User-Agent": self.config.user_agent, "Accept": "text/html,application/xhtml+xml"}
        rows: list[dict] = []
        for page in range(1, self.pages + 1):
            sep = "&" if "?" in self.list_url else "?"
            url = f"{self.list_url}{sep}pageIndex={page}"
            try:
                html = _http.get_text(url, headers=headers)
            except Exception:
                break
            page_rows = self._parse_list(html)
            if not page_rows:
                break
            rows.extend(page_rows)
            _http.polite_sleep(self.config.request_delay_sec)
            if len(rows) >= self.config.per_source_limit:
                break
        return rows[: self.config.per_source_limit]

    # ── 목록 HTML 파싱 (eGov 표준 게시판) ──────────────────────
    def _parse_list(self, html: str) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
            anchor = re.search(r"<a\b([^>]*)>(.*?)</a>", tr, re.S | re.I)
            if not anchor:
                continue
            attrs, inner = anchor.group(1), anchor.group(2)
            title = unescape(re.sub(r"<[^>]+>", "", inner)).strip()
            if not title or len(title) < 2:
                continue

            href = _attr(attrs, "href")
            onclick = _attr(attrs, "onclick")
            blob = f"{href} {onclick}"

            # 상세 글 링크인지 확인: view.do 이거나 ID 파라미터/함수 인자가 있어야 함
            detail_id = _extract_id(blob)
            is_detail = ("view.do" in href) or (detail_id is not None)
            if not is_detail:
                continue

            # 상세 URL 구성
            if href and "view.do" in href:
                detail_url = urllib.parse.urljoin(f"{self.base}{self.dir}/", href.lstrip("./"))
            else:
                detail_url = f"{self.base}{self.dir}/view.do?menuNo={self.menu_no}"
                if self.bbs_id:
                    detail_url += f"&bbsId={self.bbs_id}"
                if detail_id:
                    detail_url += f"&nttId={detail_id}"

            key = detail_id or title
            if key in seen:
                continue
            seen.add(key)

            date_m = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", tr)
            posted = (
                f"{date_m.group(1)}-{int(date_m.group(2)):02d}-{int(date_m.group(3)):02d}"
                if date_m else ""
            )
            # 목록에 별도 기관/작성처 셀이 있으면 사용, 없으면 대한체육회
            org = _cell_org(tr) or "대한체육회"
            out.append({"id": detail_id or "", "title": title, "url": detail_url,
                        "date": posted, "org": org})
        return out

    # ── 정규화 ──────────────────────────────────────────────
    def normalize(self, raw: dict) -> JobPosting | None:
        title = (raw.get("title") or "").strip()
        if not title:
            return None
        job = JobPosting(
            source=self.key,
            source_id=str(raw.get("id") or ""),
            company=raw.get("org") or "대한체육회",
            title=title,
            url=raw.get("url", ""),
            sector="협회",
            company_size="공공/협회",
            level="",
            posted_at=raw.get("date", ""),
            description="대한체육회 채용공고",
            raw=raw,
        )
        return self.enrich(job)


def _attr(attrs: str, name: str) -> str:
    m = re.search(rf'{name}\s*=\s*"([^"]*)"', attrs, re.I) or \
        re.search(rf"{name}\s*=\s*'([^']*)'", attrs, re.I)
    return m.group(1) if m else ""


def _extract_id(blob: str) -> str | None:
    for p in _ID_PARAMS:
        m = re.search(rf"{p}\D{{0,3}}(\d+)", blob)
        if m:
            return m.group(1)
    # onclick 함수 인자로 넘기는 숫자 ID: fn_view('12345') / goView(12345)
    m = re.search(r"[('\"](\d{3,})['\")]", blob)
    return m.group(1) if m else None


def _cell_org(tr: str) -> str:
    """행에 기관/주관 셀이 있으면 추출(선택). 표준 클래스 후보만 가볍게 확인."""
    m = re.search(r'<td[^>]*class="[^"]*(?:org|institution|writer|department)[^"]*"[^>]*>(.*?)</td>',
                  tr, re.S | re.I)
    if m:
        return unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
    return ""
