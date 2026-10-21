"""글 HTML → 구조 지표 (내용이 아니라 구성을 잰다).

허브 준칙: 본문 전문은 저장하지 않는다. 이 모듈은 본문 텍스트를 지역 변수로만
쓰고 숫자·참거짓 지표만 돌려준다.

본문 영역은 채널별로 알려진 컨테이너(class)를 먼저 찾고, 없으면 <article>,
그것도 없으면 <body> 전체를 본다. 블로그 스킨이 바뀌면 CONTENT_CLASSES 에
class 이름만 추가하면 된다.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from html.parser import HTMLParser

from .keywords import FORMAT_MODIFIERS

# 본문 컨테이너 class (앞에 있을수록 우선)
CONTENT_CLASSES = [
    "se-main-container",           # 네이버 스마트에디터 ONE
    "post_ct",                     # 네이버 모바일 구 에디터
    "tt_article_useless_p_margin",  # 티스토리 기본 에디터
    "entry-content",
    "article-view",
    "contents_style",
]
# 소제목으로 볼 class (네이버 스마트에디터의 소제목 컴포넌트)
HEADING_CLASSES = ["se-section-sectionTitle"]
# 태그 묶음 class (본문 밖에 있어도 센다)
TAG_AREA_CLASSES = ["post_tag", "tag_area", "tagList", "tags", "tag-list", "tag_label"]

FAQ_PATTERN = re.compile(r"FAQ|자주\s*묻는|Q\s*&\s*A|Q&A|^Q[.:\s]", re.IGNORECASE)
QUESTION_ENDINGS = ("?", "까", "나요", "가요", "인가", "을까", "할까", "죠")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr", "blockquote", "section"}


# --------------------------------------------------------------------------- #
# 제목
# --------------------------------------------------------------------------- #
def title_patterns(title: str) -> list[str]:
    """제목 패턴 라벨: 질문형 · 숫자 · 괄호 · 형식 수식어."""
    t = title.strip()
    out: list[str] = []
    if is_question(t):
        out.append("질문형")
    if re.search(r"\d", t):
        out.append("숫자")
    if re.search(r"[\[\(【「<]", t):
        out.append("괄호")
    out.extend(m for m in FORMAT_MODIFIERS if m.replace(" ", "") in t.replace(" ", ""))
    return out


def is_question(text: str) -> bool:
    t = text.strip().rstrip(".!~ ")
    return t.endswith(QUESTION_ENDINGS) or "?" in t


# --------------------------------------------------------------------------- #
# 본문
# --------------------------------------------------------------------------- #
@dataclass
class Metrics:
    lead_chars: int = 0
    lead_has_keyword: bool = False
    lead_has_number: bool = False
    headings: int = 0
    question_headings: int = 0
    body_chars: int = 0
    images: int = 0
    tables: int = 0
    lists: int = 0
    has_faq: bool = False
    external_links: int = 0
    internal_links: int = 0
    tags: int = 0
    published: str = ""
    container: str = ""        # 어떤 컨테이너로 측정했나 (디버깅용)
    heading_texts: list[str] = field(default_factory=list, repr=False)


class _Parser(HTMLParser):
    def __init__(self, container_class: str | None, use_article: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.container_class = container_class
        self.use_article = use_article
        self.stack: list[tuple[str, set[str]]] = []
        self.in_container = 0          # 컨테이너 진입 깊이 (0이면 밖)
        self.container_depth = -1
        self.in_heading = 0
        self.heading_depth = -1
        self.heading_buf: list[str] = []
        self.in_tag_area = 0
        self.tag_area_depth = -1
        self.skip = 0                  # script/style
        self.text: list[str] = []
        self.links: list[str] = []
        self.m = Metrics()

    # 헬퍼 ---------------------------------------------------------------
    def _is_container(self, tag: str, classes: set[str]) -> bool:
        if self.container_class:
            return self.container_class in classes
        if self.use_article:
            return tag == "article"
        return tag == "body"

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set((a.get("class") or "").split())

        if tag == "meta" and a.get("property") == "article:published_time":
            self.m.published = (a.get("content") or "")[:10]

        if tag in ("script", "style", "noscript"):
            self.skip += 1

        if tag not in _VOID:
            self.stack.append((tag, classes))
        depth = len(self.stack)

        if not self.in_container and self._is_container(tag, classes):
            self.in_container = 1
            self.container_depth = depth

        if not self.in_tag_area and classes & set(TAG_AREA_CLASSES):
            self.in_tag_area = 1
            self.tag_area_depth = depth
        if tag == "a" and (self.in_tag_area or "tag" in (a.get("rel") or "").split()):
            self.m.tags += 1

        if not self.in_container:
            return

        if tag in _BLOCK:
            self.text.append("\n")
        if not self.in_heading and (tag in ("h2", "h3", "h4") or classes & set(HEADING_CLASSES)):
            self.in_heading = 1
            self.heading_depth = depth
            self.heading_buf = []
        if tag == "img":
            self.m.images += 1
        if tag == "table":  # 네이버 se-table 컴포넌트도 안쪽은 <table>
            self.m.tables += 1
        if tag in ("ul", "ol"):
            self.m.lists += 1
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1
        # 잘못 닫힌 HTML 방어: 같은 태그를 만날 때까지 스택을 되감는다
        if not any(t == tag for t, _ in self.stack):
            return
        while self.stack:
            depth = len(self.stack)
            t, _ = self.stack.pop()
            if self.in_heading and depth == self.heading_depth:
                text = "".join(self.heading_buf).strip()
                if text:
                    self.m.headings += 1
                    self.m.heading_texts.append(text)
                self.in_heading = 0
            if self.in_tag_area and depth == self.tag_area_depth:
                self.in_tag_area = 0
            if self.in_container and depth == self.container_depth:
                self.in_container = 0
            if t == tag:
                break
        if tag in _BLOCK and self.in_container:
            self.text.append("\n")

    def handle_data(self, data):
        if self.skip or not self.in_container:
            return
        self.text.append(data)
        if self.in_heading:
            self.heading_buf.append(data)


def _pick_container(html: str) -> tuple[str | None, bool]:
    for cls in CONTENT_CLASSES:
        if re.search(rf'class="[^"]*\b{re.escape(cls)}\b', html):
            return cls, False
    return None, bool(re.search(r"<article[\s>]", html, re.IGNORECASE))


def analyze_html(html: str, page_url: str, keyword: str = "") -> Metrics:
    container_class, use_article = _pick_container(html)
    p = _Parser(container_class, use_article)
    p.feed(html)
    p.close()
    m = p.m
    m.container = container_class or ("article" if use_article else "body")

    # 본문 텍스트는 여기서만 쓰고 버린다 (저장 금지)
    body = re.sub(r"[ \t ​]+", " ", "".join(p.text))
    m.body_chars = len(re.sub(r"\s", "", body))
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(body) if len(s.strip()) > 1]
    lead = " ".join(sentences[:3])
    m.lead_chars = len(re.sub(r"\s", "", lead))
    m.lead_has_number = bool(re.search(r"\d", lead))
    words = [w for w in re.split(r"\s+|vs", keyword) if len(w) >= 2]
    m.lead_has_keyword = bool(words) and any(w in lead for w in words)

    m.question_headings = sum(1 for h in m.heading_texts if is_question(h))
    m.has_faq = any(FAQ_PATTERN.search(h) for h in m.heading_texts) or bool(
        re.search(r"자주\s*묻는\s*질문|FAQ", body)
    )
    m.internal_links, m.external_links = _count_links(p.links, page_url)
    return m


def _count_links(hrefs: list[str], page_url: str) -> tuple[int, int]:
    page = urllib.parse.urlsplit(page_url)
    site = _site_key(page.netloc, page.path)
    internal = external = 0
    for href in hrefs:
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        u = urllib.parse.urlsplit(urllib.parse.urljoin(page_url, href))
        if u.scheme not in ("http", "https"):
            continue
        if _site_key(u.netloc, u.path) == site:
            internal += 1
        else:
            external += 1
    return internal, external


def _site_key(netloc: str, path: str) -> str:
    """같은 블로그인지 판별할 키. 네이버는 도메인이 같아도 블로그 ID로 구분한다."""
    host = netloc.lower().removeprefix("www.")
    if host in ("blog.naver.com", "m.blog.naver.com"):
        first = path.strip("/").split("/")[0]
        return f"naver/{first}"
    return host
