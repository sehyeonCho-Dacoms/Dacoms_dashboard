"""원고 → 블로그 이미지 4장 (G5 출력 · 게시할 때 사람이 에디터에 올림).

  1_cover.png   대표 이미지(1080×1080) — 제목 + 한 줄 요약. 네이버 대표 사진·검색 미리보기용
  2_table.png   원고 첫 표를 그림으로 — 네이버에 표를 붙이면 서식이 깨지는 문제도 피한다
  3_card.png    원고 첫 목록(체크리스트·핵심 3가지)을 카드 한 장으로
  4_photo.jpg   Pixabay 스톡 사진(PIXABAY_API_KEY 가 있을 때) 또는 Wikimedia Commons CC0 사진
                (검색어는 제목·질문에서 자동, photo: 로 지정 가능)
                → 못 구하면 4_faq.png (FAQ 질문 카드)로 대신
                검색 API가 막힌 곳(429)에서는 `photo` 명령(또는 Actions '사진 찾기')으로 찾은
                photo_url·photo_page·photo_license·photo_artist 를 머리말에 넣으면 검색을 건너뛴다
  images.md     각 이미지의 alt·캡션·넣을 위치

G6 검수 준칙 3번(기사 사진·그래픽 복제 0)에 맞춰 기사 이미지는 쓰지 않는다. 숫자는 원고 표에서
다시 그린다. 글꼴은 Pretendard(SIL OFL), 처음 실행할 때 내려받아 캐시한다.
렌더링은 Playwright(Chromium). 브라우저 경로가 다르면 CHROMIUM_PATH 로 지정한다.
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .draft import Block, Draft, strip_inline

FONT_URLS = {
    "Pretendard-Regular.otf": "https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/public/static/Pretendard-Regular.otf",
    "Pretendard-Bold.otf": "https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/public/static/Pretendard-Bold.otf",
}
FONT_DIR = Path(os.getenv("GEO_FONT_DIR", Path.home() / ".cache" / "doctoron-fonts"))
UA = "DoctorOnGeoBot/0.1 (+https://doctoronhr.tistory.com)"
FREE_LICENSES = ("CC0",)   # 스톡형 CC0만. 퍼블릭 도메인은 대부분 정부 행사 사진(실존 인물·날짜)이라 뺀다
BRAND = "닥터온 · 의사 채용·연봉·이직 정보"

_CSS = """
@font-face { font-family: P; src: url('{reg}'); font-weight: 400; }
@font-face { font-family: P; src: url('{bold}'); font-weight: 700; }
* { box-sizing: border-box; margin: 0; }
body { font-family: P, 'WenQuanYi Zen Hei', sans-serif; width: 1080px; color: #14213d; background: #fff; }
.wrap { padding: 72px; }
.tag { display: inline-block; font-size: 30px; font-weight: 700; padding: 10px 22px; border-radius: 999px;
       background: #e8f1ff; color: #1d4ed8; }
.brand { font-size: 28px; color: #64748b; }
h1 { font-size: 40px; font-weight: 700; margin: 0 0 32px; line-height: 1.35; }
"""


@dataclass
class Image:
    file: str
    alt: str
    caption: str
    place: str


def _fonts() -> tuple[str, str]:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, url in FONT_URLS.items():
        p = FONT_DIR / name
        if not p.exists():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                p.write_bytes(urllib.request.urlopen(req, timeout=30).read())  # noqa: S310
            except Exception:
                pass   # 없으면 시스템 글꼴로 대체 (WenQuanYi)
        paths.append(p.as_uri() if p.exists() else "")
    return paths[0], paths[1]


def _page(body: str, extra_css: str = "") -> str:
    reg, bold = _fonts()
    css = _CSS.replace("{reg}", reg).replace("{bold}", bold)
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{css}{extra_css}</style></head><body>{body}</body></html>"


def _e(s: str) -> str:
    return html.escape(strip_inline(s))


# --------------------------------------------------------------------------- #
# 템플릿
# --------------------------------------------------------------------------- #
def cover_html(d: Draft) -> str:
    label = d.meta.get("category") or ("의사 이직·계약" if d.meta.get("target") == "의사" else "병원 실무")
    sub = d.meta.get("subtitle") or _first_sentence(d)
    return _page(f"""
<div class="cover">
  <div class="tag">{html.escape(label)}</div>
  <div class="title">{html.escape(d.title)}</div>
  <div class="sub">{html.escape(sub)}</div>
  <div class="brand">{BRAND}</div>
</div>""", """
.cover { width: 1080px; height: 1080px; padding: 96px 88px; display: flex; flex-direction: column;
         background: linear-gradient(160deg, #0f2a4a 0%, #1d4ed8 100%); color: #fff; }
.cover .tag { background: rgba(255,255,255,.16); color: #fff; align-self: flex-start; }
.cover .title { font-size: 76px; font-weight: 700; line-height: 1.25; margin-top: 64px; word-break: keep-all; }
.cover .sub { font-size: 36px; line-height: 1.5; margin-top: 40px; opacity: .9; word-break: keep-all; }
.cover .brand { margin-top: auto; color: rgba(255,255,255,.75); }
""")


def table_html(heading: str, b: Block) -> str:
    head, *rows = b.rows
    th = "".join(f"<th>{_e(c)}</th>" for c in head)
    trs = "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in r) + "</tr>" for r in rows)
    return _page(f"""
<div class="wrap">
  <h1>{_e(heading)}</h1>
  <table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>
  <div class="brand foot">자료: 닥터온 팀 정리 · 원고 본문 표를 다시 그림</div>
</div>""", """
table { width: 100%; border-collapse: collapse; font-size: 26px; line-height: 1.45; word-break: keep-all; }
th { background: #0f2a4a; color: #fff; font-weight: 700; padding: 18px 16px; text-align: left; }
td { padding: 18px 16px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
td:first-child { font-weight: 700; background: #f8fafc; width: 22%; }
.foot { margin-top: 28px; font-size: 22px; }
""")


def list_card_html(heading: str, items: list[str], mark: str = "✓") -> str:
    lis = "".join(f"<li><span class='m'>{mark}</span><span>{_e(i)}</span></li>" for i in items)
    return _page(f"""
<div class="wrap card">
  <div class="tag">한눈에 보기</div>
  <h1>{_e(heading)}</h1>
  <ul>{lis}</ul>
  <div class="brand">{BRAND}</div>
</div>""", """
.card { min-height: 1080px; display: flex; flex-direction: column; background: #f8fafc; }
.card h1 { font-size: 52px; margin-top: 36px; word-break: keep-all; }
ul { list-style: none; padding: 0; display: flex; flex-direction: column; gap: 22px; }
li { display: flex; gap: 20px; font-size: 30px; line-height: 1.45; background: #fff; border-radius: 20px;
     padding: 24px 28px; box-shadow: 0 2px 0 #e2e8f0; word-break: keep-all; }
.m { color: #1d4ed8; font-weight: 700; flex: none; }
.card .brand { margin-top: auto; padding-top: 32px; }
""")


# --------------------------------------------------------------------------- #
# 사진 — Pixabay(키가 있으면) → 없으면 Wikimedia Commons(CC0만)
# --------------------------------------------------------------------------- #
def find_photo(query: str, limit: int = 1) -> dict | list[dict] | None:
    """limit=1 이면 첫 후보(dict) 또는 None, 그보다 크면 후보 목록.

    PIXABAY_API_KEY 가 있으면 Pixabay 스톡 사진(가로)에서 찾는다. 없으면 Wikimedia Commons 의
    CC0 분류(Category:CC-zero) 안에서 먼저 찾고, 없으면 전체에서 찾는다(CC0 필터는 그대로).
    Wikimedia CC0 는 실존 인물·행사 사진이 많아 자동 선택 품질이 낮다(10/22 확인).
    """
    found: list[dict] | None = []
    if key := os.getenv("PIXABAY_API_KEY"):
        found = _pixabay(query, limit, key)
        if limit == 1:
            return found[0] if found else None
        return found or []
    for scope in (" incategory:CC-zero", ""):
        found = _search(query + scope, limit)
        if found is None or found:
            break
    if limit == 1:
        return found[0] if found else None
    return found or []


def _pixabay(query: str, limit: int, key: str) -> list[dict] | None:
    """Pixabay 검색 (Pixabay Content License: 상업적 사용 가능, 출처 표기 불필요하지만 캡션에 표기).

    Pixabay 는 이미지 직접 링크(핫링크)를 금지하므로 쓸 때는 내려받아 올린다(render·노션 업로드).
    """
    url = "https://pixabay.com/api/?" + urllib.parse.urlencode(
        {"key": key, "q": query, "image_type": "photo", "orientation": "horizontal", "safesearch": "true",
         "min_width": 1200, "per_page": max(limit, 20)})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = json.load(urllib.request.urlopen(req, timeout=20))  # noqa: S310
    except Exception as exc:
        print(f"   ⚠️  Pixabay 검색 실패({getattr(exc, 'code', type(exc).__name__)})")   # URL에 키가 있어 예외 문구는 찍지 않음
        return None
    hits = [h for h in data.get("hits", []) if "ai generated" not in h.get("tags", "").lower()]   # AI 생성 이미지 제외
    return [pixabay_item(h) for h in hits][:limit]


def pixabay_item(h: dict) -> dict:
    tags = list(dict.fromkeys(t.strip() for t in h.get("tags", "").split(",") if t.strip()))[:5]   # 중복 태그 정리
    return {"url": h.get("largeImageURL") or h.get("webformatURL", ""), "page": h.get("pageURL", ""),
            "license": "Pixabay License", "artist": (h.get("user") or "작자 미상")[:60],
            "title": ", ".join(tags) or f"Pixabay {h.get('id', '')}", "source": "Pixabay"}


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=30).read()  # noqa: S310


def photo_caption(ph: dict) -> str:
    if ph.get("source") == "Pixabay" or "pixabay.com" in ph.get("page", ""):
        return f"사진: {ph['artist']} / Pixabay {ph['page']}"
    return f"사진: {ph['artist']} / Wikimedia Commons ({ph['license']}) {ph['page']}"


def _search(query: str, limit: int) -> list[dict] | None:
    params = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": "6",
              "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": "50", "prop": "imageinfo",
              "iiprop": "url|extmetadata|size|mime", "iiurlwidth": "1280"}
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = json.load(urllib.request.urlopen(req, timeout=20))  # noqa: S310
    except Exception as exc:
        print(f"   ⚠️  Wikimedia 검색 실패({getattr(exc, 'code', exc)}) → FAQ 카드로 대신")
        return None
    pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    found: list[dict] = []
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = re.sub(r"<[^>]+>", "", meta.get("LicenseShortName", {}).get("value", ""))
        if not lic.startswith(FREE_LICENSES) or not looks_like_photo(p.get("title", ""), info):
            continue
        series = _series(p.get("title", ""))
        if any(_series(f["title"]) == series for f in found):
            continue   # 같은 묶음(스캔 01·02·13 등)은 하나만
        artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip() or "작자 미상"
        found.append({"url": info.get("thumburl") or info["url"], "page": info.get("descriptionurl", ""),
                      "license": lic, "artist": artist[:60], "title": p.get("title", "")})
        if len(found) >= limit:
            break
    return found


# 블로그 사진으로 맞지 않는 것: 스캔·문서·지도·도표·옛 자료
_NOT_PHOTO = re.compile(r"\b(img|scan|scanned|page|p\.|pp\.|document|certificate|poster|map|diagram|chart|"
                        r"logo|icon|drawing|illustration|painting|engraving|stamp|newspaper|archive|distribution|graph|"
                        r"statistics|infographic|screenshot|"
                        r"socialist|soviet|ussr|19[0-8]\d|"
                        # 행사·인물 사진 (블로그 사진으로 쓰면 실존 인물을 오해하게 만든다)
                        r"signs?|announcement|ceremony|conference|summit|governor|president|senator|minister|"
                        r"mayor|secretary|congress|parliament|election|visit|meets?|award|"
                        r"january|february|march|april|may|june|july|august|september|october|november|december)\b"
                        r"|\(\d{8,}\)", re.I)   # (7510108712) = Flickr 일괄 업로드(대개 기관 행사 사진)


def looks_like_photo(title: str, info: dict) -> bool:
    """JPEG 가로 사진(폭 1000 이상)이고, 촬영 연도가 있으면 2000년 이후."""
    w, h = info.get("width", 0), info.get("height", 1)
    if info.get("mime", "image/jpeg") != "image/jpeg" or w < 1000 or w < h:
        return False
    if _NOT_PHOTO.search(title.replace("_", " ")):
        return False
    date = info.get("extmetadata", {}).get("DateTimeOriginal", {}).get("value", "")
    year = re.search(r"(1[89]\d\d|20\d\d)", date)
    return not (year and int(year.group(1)) < 2000)


def _series(title: str) -> str:
    """'File:AUCCTU. ... img 01.jpg' → 숫자·확장자를 뺀 묶음 이름."""
    return re.sub(r"[\d_\s.\-()]+", "", title.rsplit(".", 1)[0]).lower()[:40]


def photo_from_meta(d: Draft) -> dict | None:
    """머리말에 미리 찾아 둔 사진(photo_url 등)이 있으면 그것을 쓴다."""
    if not d.meta.get("photo_url"):
        return None
    return {"url": d.meta["photo_url"], "page": d.meta.get("photo_page", ""),
            "license": d.meta.get("photo_license", ""), "artist": d.meta.get("photo_artist", "작자 미상")}


# --------------------------------------------------------------------------- #
# 실행
# --------------------------------------------------------------------------- #
def plan(d: Draft) -> list[tuple[str, str, str]]:
    """(파일, 렌더용 HTML 또는 '', 넣을 위치) — 사진은 따로 처리."""
    out = [("1_cover.png", cover_html(d), "글 맨 위 (대표 이미지로 지정)")]
    heading = d.title
    table_done = False
    best_list: tuple[str, Block] | None = None   # 카드는 항목이 가장 많은 목록(체크리스트)으로
    for b in d.blocks:
        if b.kind == "heading":
            heading = b.text
        elif b.kind == "table" and not table_done and b.rows:
            out.append(("2_table.png", table_html(heading, b), f"'{strip_inline(heading)}' 소제목 아래"))
            table_done = True
        elif b.kind == "list" and (best_list is None or len(b.items) > len(best_list[1].items)):
            best_list = (heading, b)
    if best_list:
        h, b = best_list
        out.append(("3_card.png", list_card_html(h, b.items), f"'{strip_inline(h)}' 소제목 아래"))
    return out


def render(d: Draft, out_dir: Path) -> list[Image]:
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = plan(d)
    images: list[Image] = []
    alts = {"1_cover.png": f"{d.title} 대표 이미지", "2_table.png": "비교표", "3_card.png": "핵심 정리 카드"}

    # 자동 검색은 Pixabay 키가 있을 때만. Wikimedia CC0 자동 선택은 판화·도표·정치인 사진이 나와 쓰지 않는다
    # (10/22·10/26 확인). 키가 없으면 FAQ 카드로 두고, 사진은 노션 행의 '사진 후보'(매일 Actions)에서 고른다.
    if not (photo := photo_from_meta(d)) and os.getenv("PIXABAY_API_KEY"):
        from .photos import queries_for   # photo: 가 없으면 제목·질문에서 검색어를 만든다
        for q in [d.meta["photo"]] if d.meta.get("photo") else queries_for(d.title, d.meta.get("question", "")):
            if photo := find_photo(q):
                break
    if photo is None:
        faqs = [b.text for b in d.blocks if b.kind == "heading" and b.text.startswith("Q.")]
        if faqs:
            jobs.append(("4_faq.png", list_card_html("자주 묻는 질문", [q[2:].strip() for q in faqs], "Q"),
                         "'자주 묻는 질문' 소제목 아래"))
            alts["4_faq.png"] = "자주 묻는 질문 카드"

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH") or None)
        page = browser.new_page(viewport={"width": 1080, "height": 1080}, device_scale_factor=1)
        for name, doc, place in jobs:
            page.set_content(doc, wait_until="load")
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(out_dir / name), full_page=True)
            cap = "그래픽: 닥터온 팀 제작"
            images.append(Image(name, alts.get(name, name), cap, place))
        browser.close()

    if photo:
        try:
            (out_dir / "4_photo.jpg").write_bytes(download(photo["url"]))
            images.append(Image("4_photo.jpg", d.meta.get("photo_alt") or d.meta.get("photo") or photo.get("title", "사진"),
                                photo_caption(photo), "첫 소제목 아래"))
        except Exception as exc:
            print(f"   ⚠️  사진 내려받기 실패({getattr(exc, 'code', type(exc).__name__)}) → 사진 없이 진행")

    lines = [f"# 이미지 — {d.title}", "", "| 파일 | 넣을 위치 | 설명(alt) | 캡션 |", "| --- | --- | --- | --- |"]
    lines += [f"| {i.file} | {i.place} | {i.alt} | {i.caption} |" for i in images]
    (out_dir / "images.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return images


def _first_sentence(d: Draft) -> str:
    para = next((b.text for b in d.blocks if b.kind == "para" and not b.text.startswith(("※", "["))), "")
    s = re.split(r"(?<=[.?!])\s", strip_inline(para))[0]
    return s if len(s) <= 70 else s[:68] + "…"
