"""G1-Q 질문 검수 노드 (D-056, 11/5 세현 결정) — 질문 은행 '바로 가능' 재고를 사람 대신 채운다.

  흐름: G0 기사 수집 → [G1-Q] → G2 채점 → G3 체인 행
  1) 노션 'GEO 질문 은행'의 '답 준비도'를 읽어 G2 질문 목록(g2.QUESTIONS)에 덮어쓴다.
     → 사람이 노션에서 바꾼 값(되돌리기 포함)이 그날 바로 G2에 반영된다. 못 읽으면 코드 사본 그대로.
  2) 아직 글이 없는 '바로 가능' 질문이 REFILL_AT(5개)보다 적으면, '근거 필요' 질문을 P1→P2→P3 순으로 검수한다.
  3) 검수 = 규칙 + 검색 근거 (Claude API 없음):
       - 네이버 뉴스 검색에 질문의 매칭 단어를 넣고, 매칭 단어가 제목·요약에 실제로 있는 기사만 센다.
       - 서로 다른 언론사(도메인) PASS_DOMAINS(3)곳 이상 + 그중 의료 전문지·공공기관 1곳 이상이면 통과.
  4) 통과 → '답 준비도'를 '바로 가능'으로 바꾸고 메모에 근거 출처를 한 줄 남긴다. 슬랙에는 ⏸ 보고
     (사람이 볼 일 · 다음 날 오전까지, D-046·D-047). 이상하면 세현 님이 '근거 필요'로 되돌리고 메모에 '검수 제외'.
     미달 → 메모에 '미달' 한 줄만 남기고, 7일 동안 다시 보지 않는다.

  자동으로 올리지 않는 것: '확정값 필요'(회사가 정할 값), 닥터온이 들어간 질문, 메모에 '검수 제외'가 있는 질문.
  새 질문은 만들지 않는다(11/5 세현: 있는 질문 올리기만).
"""

from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from . import _http, g2
from .notify import alert

API = "https://api.notion.com/v1"
DEFAULT_QBANK_DB = "91d69623fe3e49d08ff98b585fd49688"   # 노션 'GEO 질문 은행'
READY, NEED, FIXED = "바로 가능", "근거 필요", "확정값 필요"
PASS_DOMAINS = 3      # 서로 다른 언론사 수
RECHECK_DAYS = 7      # 미달 질문을 다시 보는 간격
MAX_CHECKS = 10       # 한 번에 검수할 질문 수 (API 호출을 아끼려고)
SKIP_MARK = "검수 제외"
TAG = "G1-Q"

# 의료 전문지·공공기관 — 통과에 1곳 이상 필요 (일반 언론만으로는 통과시키지 않는다)
TRUSTED = (
    "doctorsnews.co.kr", "docdocdoc.co.kr", "medigatenews.com", "dailymedi.com", "bosa.co.kr",
    "medipana.com", "medicaltimes.com", "mdtoday.co.kr", "monews.co.kr", "rapportian.com",
    "medifonews.com", "kormedi.com", "hitnews.co.kr", "medicalworldnews.co.kr", "healthinnews.co.kr",
    "nursenews.co.kr", "whosaeng.com", "medisobizanews.com",
)
PUBLIC_SUFFIX = (".go.kr", ".or.kr")


@dataclass
class BankRow:
    gq: int
    page_id: str
    ready: str
    memo: str


@dataclass
class Verdict:
    gq: int
    passed: bool
    domains: list[str]
    trusted: list[str]
    urls: list[str]

    def memo_line(self, day: str) -> str:
        if self.passed:
            return (f"{day} {TAG} 검수 통과 → 바로 가능 · 근거 {len(self.domains)}곳 "
                    f"(전문지·공공 {', '.join(self.trusted)}) · {' '.join(self.urls[:3])}")
        return f"{day} {TAG} 검수 미달 · 근거 {len(self.domains)}곳 (전문지·공공 {len(self.trusted)}곳)"


# --------------------------------------------------------------------------- #
# 판정 (순수 함수 — 테스트 대상)
# --------------------------------------------------------------------------- #
def domain_of(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_trusted(domain: str) -> bool:
    return any(domain == t or domain.endswith("." + t) for t in TRUSTED) or domain.endswith(PUBLIC_SUFFIX)


_TAG_RE = re.compile(r"<[^>]+>")


def judge(q: g2.Question, items: list[dict]) -> Verdict:
    """뉴스 검색 결과 → 판정. 매칭 단어가 제목·요약에 있는 기사만, 언론사(도메인)별로 1개씩 센다."""
    seen: dict[str, str] = {}
    for it in items:
        text = _TAG_RE.sub("", f"{it.get('title', '')} {it.get('description', '')}")
        if not any(t.strip() and t.strip() in text for t in q.terms):
            continue
        url = it.get("originallink") or it.get("link") or ""
        d = domain_of(url)
        if d and d not in seen:
            seen[d] = url
    domains = list(seen)
    trusted = [d for d in domains if is_trusted(d)]
    urls = [seen[d] for d in trusted] + [seen[d] for d in domains if d not in trusted]
    return Verdict(q.gq, len(domains) >= PASS_DOMAINS and bool(trusted), domains, trusted, urls)


def eligible(q: g2.Question, row: BankRow | None, written: set[int], now: datetime) -> bool:
    if q.ready != NEED or q.gq in written or "닥터온" in q.text:
        return False
    memo = row.memo if row else ""
    if SKIP_MARK in memo:
        return False
    for m in re.finditer(rf"(\d{{4}}-\d{{2}}-\d{{2}}) {TAG} 검수 미달", memo):
        if now.date() - datetime.strptime(m.group(1), "%Y-%m-%d").date() < timedelta(days=RECHECK_DAYS):
            return False
    return True


def plan(written: set[int], rows: dict[int, BankRow], now: datetime) -> tuple[int, list[g2.Question]]:
    """(채워야 할 개수, 검수할 질문 순서). 재고가 기준 이상이면 (0, [])."""
    need = g2.REFILL_AT - len(g2.ready_left(written))
    if need <= 0:
        return 0, []
    pool = [q for q in g2.QUESTIONS if eligible(q, rows.get(q.gq), written, now)]
    pool.sort(key=lambda q: (g2.PRIORITY_ORDER.get(q.priority, 9), q.gq))
    return need, pool[:MAX_CHECKS]


def apply_bank(rows: dict[int, BankRow]) -> list[int]:
    """노션 '답 준비도'를 g2.QUESTIONS 에 덮어쓴다. 바뀐 GQ 번호 목록."""
    changed = []
    for i, q in enumerate(g2.QUESTIONS):
        r = rows.get(q.gq)
        if r and r.ready in (READY, NEED, FIXED) and r.ready != q.ready:
            g2.QUESTIONS[i] = replace(q, ready=r.ready)
            changed.append(q.gq)
    g2.BY_ID.clear()
    g2.BY_ID.update({q.gq: q for q in g2.QUESTIONS})
    return changed


# --------------------------------------------------------------------------- #
# 노션·네이버 접속
# --------------------------------------------------------------------------- #
def _plain(prop: dict) -> str:
    return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []) or prop.get("title", []))


def _gq_of(prop: dict) -> int | None:
    uid = prop.get("unique_id") or {}
    if uid.get("number") is not None:
        return int(uid["number"])
    if prop.get("number") is not None:
        return int(prop["number"])
    return None


def load_bank(headers: dict, db: str) -> dict[int, BankRow]:
    rows: dict[int, BankRow] = {}
    body: dict = {"page_size": 100}
    while True:
        res = _http.request_json("POST", f"{API}/databases/{db}/query", body, headers=headers)
        for r in res.get("results", []):
            p = r.get("properties", {})
            gq = _gq_of(p.get("질문 ID", {}))
            if gq is None:
                continue
            ready = ((p.get("답 준비도") or {}).get("select") or {}).get("name", "")
            rows[gq] = BankRow(gq, r["id"], ready, _plain(p.get("메모", {})))
        if not res.get("has_more"):
            return rows
        body["start_cursor"] = res["next_cursor"]


def search_news(config, q: g2.Question) -> list[dict]:
    from .sources.naver import naver_headers
    from .sources.news import NEWS_ENDPOINTS

    url = config.naver_news_endpoint or NEWS_ENDPOINTS[config.naver_api_mode]
    items: list[dict] = []
    for term in [t.strip() for t in q.terms if t.strip()][:3]:
        data = _http.get_json(url, params={"query": term, "display": 50, "start": 1, "sort": "sim"},
                              headers=naver_headers(config))
        items.extend(data.get("items") or [])
        _http.polite_sleep(config.request_delay_sec)
    return items


def _memo_payload(old: str, line: str) -> dict:
    text = (old.rstrip() + "\n" + line).strip() if old else line
    if len(text) > 1900:          # 노션 rich_text 한 조각 2000자
        text = text[-1900:]
    return {"rich_text": [{"type": "text", "text": {"content": text}}]}


# --------------------------------------------------------------------------- #
# 실행
# --------------------------------------------------------------------------- #
def run(config, now: datetime, written: set[int] | None, dry_run: bool = False) -> list[str]:
    """G0 안에서 G2 직전에 부른다. 로그 줄 목록을 돌려준다(⏸ 줄은 슬랙으로 감)."""
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return [f"   {TAG}: NOTION_TOKEN 이 없어 질문 은행을 못 읽음 → 코드 사본으로 채점"]
    h = {"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28"}
    db = os.getenv("NOTION_QBANK_DB", DEFAULT_QBANK_DB)
    try:
        rows = load_bank(h, db)
    except Exception as exc:
        code = getattr(exc, "code", type(exc).__name__)
        hint = {404: "질문 은행 DB에 통합이 연결되지 않음 (DB 페이지 ⋯ → 연결 → 통합 추가)"}.get(code, "토큰·DB 확인")
        return [alert(TAG, f"질문 은행 읽기 실패({code}) · 코드 사본으로 채점", hint)]
    changed = apply_bank(rows)
    out = [f"🧪 {TAG}: 질문 은행 {len(rows)}개 읽음" + (f" · 노션 값 반영 {len(changed)}개" if changed else "")]
    if written is None:
        return out + ["   체인 DB를 못 읽어 재고를 모름 → 검수 건너뜀"]
    need, todo = plan(written, rows, now)
    if need <= 0:
        return out + ["   '바로 가능' 재고가 기준 이상 → 검수 안 함"]
    if not todo:   # 모자란 재고는 뒤의 G2 재고 줄(⏸)이 알린다
        return out + ["   검수할 '근거 필요' 질문이 없음 (7일 안 미달·검수 제외·확정값 필요 제외)"]
    day = now.strftime("%Y-%m-%d")
    promoted: list[Verdict] = []
    for q in todo:
        if len(promoted) >= need:
            break
        try:
            v = judge(q, search_news(config, q))
        except Exception as exc:
            out.append(f"   ⚠️  GQ-{q.gq} 검색 실패({getattr(exc, 'code', type(exc).__name__)}) → 다음 질문")
            continue
        row = rows.get(q.gq)
        out.append(f"   GQ-{q.gq} {'통과' if v.passed else '미달'} · 언론사 {len(v.domains)}곳 · 전문지·공공 {len(v.trusted)}곳")
        if dry_run or not row:
            if v.passed:
                promoted.append(v)
            continue
        props = {"메모": _memo_payload(row.memo, v.memo_line(day))}
        if v.passed:
            props["답 준비도"] = {"select": {"name": READY}}
        try:
            _http.request_json("PATCH", f"{API}/pages/{row.page_id}", {"properties": props}, headers=h)
        except Exception as exc:
            out.append(f"   ⚠️  GQ-{q.gq} 노션 쓰기 실패({getattr(exc, 'code', type(exc).__name__)})")
            continue
        if v.passed:
            promoted.append(v)
            for i, x in enumerate(g2.QUESTIONS):
                if x.gq == q.gq:
                    g2.QUESTIONS[i] = replace(x, ready=READY)
    g2.BY_ID.update({q.gq: q for q in g2.QUESTIONS})
    if promoted:
        what = ", ".join(f"GQ-{v.gq}(근거 {len(v.domains)}곳)" for v in promoted)
        out.append(alert(TAG, f"질문 자동 승격{' 예정(dry-run)' if dry_run else ''} {what}",
                         f"이상하면 질문 은행에서 '{NEED}'로 되돌리고 메모에 '{SKIP_MARK}'", owner="세현"))
    return out   # 그래도 모자라면 뒤의 G2 재고 줄(⏸)이 알린다
