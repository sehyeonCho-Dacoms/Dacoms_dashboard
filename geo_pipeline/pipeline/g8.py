"""G8 색인·반응 측정 (DR-GEO-07) — 11/2 세현 결정(D-025): API로 잴 수 있는 것은 Actions가 잰다.

  체인 DB에서 게시 URL이 있는 글 → 게시일 기준 D+3 · D+7 · D+30 중 아직 안 잰 가장 늦은 시점 1개를 잰다
  (밀린 글은 D+3을 건너뛰고 D+7부터. 실제 경과일은 기록에 '실측 D+n'으로 남긴다).

  - 네이버 글: 네이버 검색 API(블로그)에 제목을 넣어 우리 글(logNo)이 나오는지 → '색인 여부'
               조회수는 API가 없어 재지 않는다(웅서 Claude가 월요일에 네이버 블로그 통계로 채움).
  - 티스토리 글: Search Console URL 검사 API → '색인 여부' · GA4 Data API(블로그 속성) → '조회수 D+7/D+30'

  쓰는 칸(D-025로 추가): 색인 여부 · 조회수 D+7 · 조회수 D+30 · 측정 기록(한 줄 추가만).
  상태는 '게시완료' → '색인확인'만 바꾼다(색인 확인일 때). 사람확인 등 다른 상태는 건드리지 않는다.
  '확인'을 '미확인'으로 되돌리지 않는다(검색 순위가 흔들려도 한 번 색인된 글).

  11/5 세현 결정(D-041·D-026): 같은 실행에서 모든 행의 상태값과 게시 기록을 대조하고(불일치는 🔔),
  근거수집·원고작성에서 24시간 넘게 멈춘 행을 알린다. 고치지는 않는다(어느 쪽이 맞는지 사람이 정함).

Secrets: NOTION_TOKEN · NAVER_CLIENT_ID/SECRET · GSC_GA4_SA_KEY(서비스 계정 JSON 전체)
Variables(선택): GSC_SITE_URL(기본 https://doctoronhr.tistory.com/) · GA4_PROPERTY_ID(기본 559499976)
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from . import _http, notify
from .g3 import _plain, _query
from .notion import DEFAULT_DB, VERSION, _text

NOTION = "https://api.notion.com/v1"
CHECKPOINTS = (3, 7, 30)
LIVE = {"게시완료", "색인확인", "인용점검", "분석완료", "사람확인"}
SITE_URL = "https://doctoronhr.tistory.com/"
GA4_PROPERTY = "559499976"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly",
          "https://www.googleapis.com/auth/analytics.readonly"]


@dataclass
class Post:
    page_id: str
    no: str
    channel: str
    title: str
    url: str
    published: date
    state: str
    index: str
    log: str

    @property
    def naver(self) -> bool:
        return self.channel == "네이버 블로그"


@dataclass
class Measure:
    checkpoint: int
    age: int
    found: bool | None          # None = 못 잼(인증·API 오류)
    views: int | None = None
    note: str = ""


def from_row(r: dict) -> Post | None:
    p = r.get("properties", {})
    g = lambda k: _plain(p.get(k, {}))
    url, day = g("게시 URL").strip(), g("게시일")[:10]
    if not url or not day:
        return None
    return Post(page_id=r["id"], no=g("글 번호"), channel=g("채널"), title=g("제목"), url=url,
                published=date.fromisoformat(day), state=g("상태"), index=g("색인 여부"), log=g("측정 기록"))


# --------------------------------------------------------------------------- #
# 언제 잴까
# --------------------------------------------------------------------------- #
def done_checkpoints(log: str) -> set[int]:
    """측정 기록의 'G8 D+n' 중 정식 시점(3·7·30)만. 수동 기록 'D+11' 같은 값은 시점으로 치지 않는다."""
    return {int(n) for n in re.findall(r"G8 D\+(\d+)", log) if int(n) in CHECKPOINTS}


def due(post: Post, today: date) -> int | None:
    age = (today - post.published).days
    last = max(done_checkpoints(post.log), default=0)   # 늦은 시점을 이미 쟀으면 앞 시점은 건너뛴 것으로 본다
    todo = [cp for cp in CHECKPOINTS if last < cp <= age]
    return max(todo) if todo else None


# --------------------------------------------------------------------------- #
# 네이버: 검색 API에 우리 글이 나오나
# --------------------------------------------------------------------------- #
def log_no(url: str) -> str:
    m = re.search(r"(?:logNo=|/)(\d{9,})", url)
    return m.group(1) if m else ""


def naver_found(items: list[dict], url: str) -> bool:
    no = log_no(url)
    return bool(no) and any(no in (it.get("link") or "") for it in items)


def naver_search(title: str) -> list[dict]:
    from .config import Config
    from .sources.naver import ENDPOINTS, naver_headers

    cfg = Config()
    endpoint = cfg.naver_blog_endpoint or ENDPOINTS[cfg.naver_api_mode]
    data = _http.get_json(endpoint, params={"query": title, "display": 100, "start": 1, "sort": "sim"},
                          headers=naver_headers(cfg))
    return data.get("items") or []


# --------------------------------------------------------------------------- #
# 티스토리: Search Console · GA4
# --------------------------------------------------------------------------- #
def google_token() -> str | None:
    raw = os.getenv("GSC_GA4_SA_KEY")
    if not raw:
        return None
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    creds.refresh(Request())
    return creds.token


def gsc_inspect(url: str, token: str) -> tuple[bool, str]:
    site = os.getenv("GSC_SITE_URL") or SITE_URL
    res = _http.post_json("https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
                          {"inspectionUrl": url, "siteUrl": site, "languageCode": "ko-KR"},
                          headers={"Authorization": f"Bearer {token}"})
    st = res.get("inspectionResult", {}).get("indexStatusResult", {})
    return st.get("verdict") == "PASS", st.get("coverageState", "")


def tistory_paths(url: str) -> list[str]:
    path = urllib.parse.urlsplit(url).path.rstrip("/") or "/"
    m = re.fullmatch(r"/(?:m/)?(.+)", path)
    tail = m.group(1) if m else path.lstrip("/")
    return [f"/{tail}", f"/m/{tail}"]


def ga4_views(url: str, since: date, token: str) -> int:
    prop = os.getenv("GA4_PROPERTY_ID") or GA4_PROPERTY
    body = {"dateRanges": [{"startDate": since.isoformat(), "endDate": "today"}],
            "dimensions": [{"name": "pagePath"}], "metrics": [{"name": "screenPageViews"}],
            "dimensionFilter": {"filter": {"fieldName": "pagePath",
                                           "inListFilter": {"values": tistory_paths(url)}}}}
    res = _http.post_json(f"https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport", body,
                          headers={"Authorization": f"Bearer {token}"})
    return sum(int(r["metricValues"][0]["value"]) for r in res.get("rows", []))


# --------------------------------------------------------------------------- #
# 결과 → 노션 칸
# --------------------------------------------------------------------------- #
def decide(post: Post, m: Measure, today: date) -> tuple[dict, str]:
    """(노션 properties, 측정 기록에 붙일 한 줄)."""
    props: dict = {}
    if m.found is True:
        index = "확인"
    elif m.found is False:
        index = "안 잡힘" if m.checkpoint >= 7 else "미확인"
    else:
        index = None
    if index and not (post.index == "확인" and index != "확인"):
        props["색인 여부"] = {"select": {"name": index}}
    if index == "확인" and post.state == "게시완료":
        props["상태"] = {"select": {"name": "색인확인"}}
    if m.views is not None and m.checkpoint in (7, 30):
        props[f"조회수 D+{m.checkpoint}"] = {"number": m.views}

    where = "네이버 검색" if post.naver else "구글"
    seen = {True: f"{where} 노출 확인" if post.naver else "구글 색인 확인",
            False: f"{where} 안 나옴" if post.naver else "구글 미색인", None: f"{where} 측정 실패"}[m.found]
    views = (" · 조회 미측정(네이버 통계는 웅서 월요일)" if post.naver
             else f" · 조회 {m.views}" if m.views is not None else " · 조회 측정 실패")
    when = f"G8 D+{m.checkpoint}" + (f"(실측 D+{m.age})" if m.age != m.checkpoint else "")
    line = f"{today:%m/%d} {when} 자동: {seen}{views}" + (f" · {m.note}" if m.note else "")
    return props, line


def write(post: Post, props: dict, line: str, h: dict) -> None:
    log = f"{post.log}\n{line}" if post.log else line
    props = {**props, "측정 기록": {"rich_text": _text(log)}}
    _http.request_json("PATCH", f"{NOTION}/pages/{post.page_id}", {"properties": props}, headers=h)


# --------------------------------------------------------------------------- #
# 실행
# --------------------------------------------------------------------------- #
def measure(post: Post, cp: int, today: date, gtoken: str | None) -> Measure:
    m = Measure(cp, (today - post.published).days, None)
    if post.naver:
        m.found = naver_found(naver_search(post.title), post.url)
        return m
    if not gtoken:
        m.note = "GSC_GA4_SA_KEY 없음"
        return m
    m.found, m.note = gsc_inspect(post.url, gtoken)
    m.views = ga4_views(post.url, post.published, gtoken)
    return m


# --------------------------------------------------------------------------- #
# 상태값 대조 · 정체 (D-041, D-026 — 11/5 세현 결정). 고치지 않고 알리기만 한다.
# 사람확인인데 공개된 글처럼 '어느 쪽이 맞는지' 사람이 봐야 하는 경우가 섞여 있어서다(D-031은 되돌릴 수 있는
# 정정만 허용하지만, 상태를 올릴지 글을 내릴지는 판단이 필요).
# --------------------------------------------------------------------------- #
BEFORE_POST = {"근거수집", "원고작성", "검수통과"}
AFTER_POST = LIVE - {"사람확인"}
STALL = {"근거수집", "원고작성"}
STALL_HOURS = 24


def audit(rows: list[dict], now: datetime) -> list[str]:
    if now.tzinfo is None:   # 테스트·수동 실행에서 시간대 없이 들어오면 KST로 본다
        now = now.replace(tzinfo=timezone(timedelta(hours=9)))
    mismatch, stalled = [], []
    for r in rows:
        p = r.get("properties", {})
        g = lambda k: _plain(p.get(k, {})).strip()
        no, state, url, day = g("글 번호"), g("상태"), g("게시 URL"), g("게시일")
        if (url or day) and state in BEFORE_POST:
            mismatch.append(f"{no} 게시 기록이 있는데 상태 '{state}'")
        elif url and state == "사람확인":
            mismatch.append(f"{no} 상태 '사람확인'인데 게시 URL 있음(공개 여부 확인)")
        elif state in AFTER_POST and not url:
            mismatch.append(f"{no} 상태 '{state}'인데 게시 URL 없음")
        elif bool(url) != bool(day):
            mismatch.append(f"{no} 게시 URL·게시일 중 하나만 있음")
        made = r.get("created_time", "")
        if state in STALL and made:
            hours = (now - datetime.fromisoformat(made.replace("Z", "+00:00"))).total_seconds() / 3600
            if hours > STALL_HOURS:
                stalled.append(f"{no} {state} {int(hours // 24)}일째")
    out = [f"   ⚠️ {m}" for m in mismatch] + [f"   ⏳ {s}" for s in stalled]
    if mismatch:
        out.append(notify.alert("G7·G8", f"상태값과 게시 기록 불일치 {len(mismatch)}건",
                                "손댄 사람이 상태값을 바꾸고 작업 기록 1줄(D-041)", owner="손댄 사람"))
    if stalled:
        out.append(notify.alert("G4~G6", f"하루 넘게 멈춘 행 {len(stalled)}개({', '.join(s.split()[0] for s in stalled)})",
                                "작업키트 세션 열기 · 막힌 이유를 작업 기록에"))
    return out


def run(now: datetime, dry_run: bool = False, today: date | None = None, pause: float = 0.4) -> list[str]:
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return ["❌ G8: NOTION_TOKEN 이 없음"]
    h = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}
    db = os.getenv("NOTION_GEO_DB", DEFAULT_DB)
    today = today or now.date()
    every = _query(db, {}, h)   # 대조는 모든 행, 측정은 게시 URL이 있는 행만
    rows = [r for r in every if _plain(r.get("properties", {}).get("게시 URL", {})).strip()]
    posts = [p for r in rows if (p := from_row(r)) and p.state in LIVE]
    todo = [(p, cp) for p in posts if (cp := due(p, today))]
    out = [f"📏 G8 {today}: 게시 글 {len(posts)}편 · 오늘 잴 글 {len(todo)}편" + (" [dry-run]" if dry_run else "")]

    gtoken = None
    if any(not p.naver for p, _ in todo):
        try:
            gtoken = google_token()
            if not gtoken:
                out.append("   ⚠️ GSC_GA4_SA_KEY 가 없어 티스토리 색인·조회수는 건너뜀")
        except Exception as exc:
            out.append(f"❌ 구글 서비스 계정 인증 실패: {type(exc).__name__}")

    fails = 0
    for p, cp in sorted(todo, key=lambda x: x[0].no):
        try:
            m = measure(p, cp, today, gtoken)
        except Exception as exc:
            code = getattr(exc, "code", type(exc).__name__)
            hint = {403: "권한 없음 또는 API 사용 안 함(GCP에서 Search Console API·Analytics Data API 사용 설정)",
                    401: "인증 오류", 429: "호출 한도"}.get(code, "")
            out.append(f"   ⚠️ {p.no} 측정 실패 ({code}) {hint}")
            fails += 1
            continue
        props, line = decide(p, m, today)
        out.append(f"   {p.no} {line[6:]}")
        if not dry_run:
            write(p, props, line, h)
            time.sleep(pause)   # 노션 API 초당 3회
    if fails and fails == len(todo):
        out.append("❌ 잴 글을 하나도 못 쟀음 → 위 오류 확인")
    checks = audit(every, now)
    out.append(f"🔎 상태값 대조·정체 확인: {'이상 없음' if not checks else '아래'}")
    return out + checks
