"""G6 원고 검수 — 자동 사전 검수 (원고 .md 또는 게시된 글 URL).

블로그 GEO 체인의 G6 검수 준칙 v0(8개) 중 코드로 볼 수 있는 것을 먼저 거른다.
판정은 세 단계:
  위반  — 고치기 전에는 게시하지 않는다 (예: 기사 캡처 이미지, 클릭 안 되는 출처)
  확인  — 사람이 원문과 대조하거나 판단한다 (예: 직함, 입장, 닥터온 숫자)
  권장  — 형식 개선 (예: 출처 날짜, 소제목 수)
'우리만의 관점(7번)'은 기계로 판단할 수 없어 항상 사람 몫이다.

규칙은 10/22 첫 두 글(티스토리 T-001 · 네이버 N-001) 검수에서 실제로 나온 문제를 기준으로 만들었다.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from html.parser import HTMLParser

from .draft import Draft
from .screen import CONTROVERSY_TERMS, LEGAL_TERMS
from .structure import _pick_container

VIOLATION, CHECK, SUGGEST = "위반", "확인", "권장"

# 3번: 기사 사진·그래픽 복제
CAPTURE_WORDS = ["캡처", "캡쳐", "스크린샷", "기사 화면", "기사 이미지"]
FREE_IMAGE_SOURCES = ["CC0", "CC BY", "Wikimedia", "Unsplash", "Pixabay", "직접", "자체", "닥터온"]
# 8번: 의료 조언
ADVICE_WORDS = ["복용하세요", "드세요", "처방받으세요", "치료받으세요", "진료받으세요", "검사받으세요", "약을 끊"]
# 입장(DR-MKT-02 사람 확인) — 점수 준칙의 논쟁 단어 + 평가 표현
STANCE_WORDS = ["호재", "악재", "협상 카드", "잘못된 정책", "졸속", "환영할 만"]
# 직함 — 원문과 대조해야 하는 사람 이름 + 직함. '의원'은 병·의원(clinic)과 겹쳐서
# 이름은 흔한 성으로 시작하는 2~3글자만 사람으로 본다 (10/22: '검진 의원'·'우리 의원'이 걸렸음)
_TITLES = r"[가-힣]{0,8}(?:위원장|장관|차관|의원|협회장|회장|청장|이사장)"
_NAME = r"[김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노하곽성차주우구민진나지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용예봉경사부][가-힣]{1,2}"
_AFTER = r"(?=[이가은는의을를과와도에께]|\s|$|[,.·()])"   # 직함 뒤 조사 허용 ('이만희 의원이')
_NAME_TITLE = re.compile(rf"(?<![가-힣])({_NAME})\s+(?:국회\s*)?({_TITLES}){_AFTER}")
_TITLE_NAME = re.compile(rf"({_TITLES})\s+({_NAME})(?=\s|$|[,.·(])")
_NOT_NAMES = {"우리", "이번", "이런", "이와", "정부", "지역", "소속", "해당", "전국", "전체", "기존", "신규",
              "일반", "동네", "한방", "개인", "전문", "동물", "주요", "일부", "다른", "모든", "각각", "유명",
              "현직", "전직", "국회", "정부", "신임", "초대", "공동", "부의", "여당", "야당", "국민", "지방", "서울", "경기"}
_DATE = re.compile(r"20\d\d[.\-/년]\s?\d{1,2}")
_URL_TEXT = re.compile(r"https?://\S+")
_SENT = re.compile(r"(?<=[.?!])\s+|\n+")


@dataclass
class Finding:
    rule: str        # 준칙 번호 또는 항목
    level: str       # 위반 | 확인 | 권장
    message: str


@dataclass
class Doc:
    """검수 대상의 공통 모양 (원고든 게시 글이든)."""

    title: str
    channel: str
    text: str
    headings: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)      # (글자, 주소)
    images: list[tuple[str, str]] = field(default_factory=list)     # (alt, 캡션)
    tags: list[str] = field(default_factory=list)
    tables: int = 0

    def sentences(self) -> list[str]:
        return [s.strip() for s in _SENT.split(self.text) if len(s.strip()) >= 10]


def from_draft(d: Draft) -> Doc:
    return Doc(
        title=d.title,
        channel=d.channel,
        text=d.plain_text(),
        headings=[b.text for b in d.blocks if b.kind == "heading"],
        links=d.links(),
        images=[(b.alt, b.caption) for b in d.blocks if b.kind == "image"],
        tags=d.tags,
        tables=sum(1 for b in d.blocks if b.kind == "table"),
    )


class _HtmlDoc(HTMLParser):
    def __init__(self, container: str | None, use_article: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.container, self.use_article = container, use_article
        self.depth = 0
        self.inside = -1
        self.skip = 0
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.images: list[list[str]] = []
        self.pending_caption = False
        self.link_href: str | None = None
        self.link_text: list[str] = []
        self.tables = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag in ("script", "style"):
            self.skip += 1
        if tag not in ("img", "br", "meta", "link", "input", "hr", "source"):
            self.depth += 1
        if self.inside < 0 and ((self.container and self.container in classes)
                                or (not self.container and tag == ("article" if self.use_article else "body"))):
            self.inside = self.depth
        if self.inside < 0:
            return
        if tag in ("p", "div", "li", "tr", "h2", "h3", "h4", "br", "figcaption"):
            self.text.append("\n")
        if tag == "table":
            self.tables += 1
        if tag == "img":
            self.images.append([a.get("alt") or "", ""])
            self.pending_caption = True
        if tag == "a" and (a.get("href") or "").startswith("http"):
            self.link_href, self.link_text = a["href"], []

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        if tag == "a" and self.link_href:
            self.links.append(("".join(self.link_text).strip(), self.link_href))
            self.link_href = None
        if tag in ("img", "br", "meta", "link", "input", "hr", "source"):
            return
        if self.depth == self.inside:
            self.inside = -2          # 컨테이너 끝 (다시 들어가지 않음)
        self.depth -= 1

    def handle_data(self, data):
        if self.skip or self.inside < 0:
            return
        self.text.append(data)
        if self.link_href is not None:
            self.link_text.append(data)
        s = data.strip()
        if self.pending_caption and s:
            if len(s) <= 80 and re.match(r"^(출처|사진|자료|이미지)\s*[:：]", s):
                self.images[-1][1] = s
            self.pending_caption = False


def from_html(html: str, url: str = "", channel: str = "") -> Doc:
    from .structure import analyze_html

    container, use_article = _pick_container(html)
    p = _HtmlDoc(container, use_article)
    p.feed(html)
    text = re.sub(r"[ \t ​]+", " ", "".join(p.text))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    m = analyze_html(html, url)
    title = ""
    if t := re.search(r'<meta property="og:title" content="([^"]*)"', html):
        title = t.group(1)
    if not channel:
        host = urllib.parse.urlsplit(url).netloc
        channel = "naver" if "naver" in host else "tistory" if "tistory" in host else ""
    return Doc(title=title, channel=channel, text=text, headings=m.heading_texts,
               links=p.links, images=[(a, c) for a, c in p.images], tables=p.tables,
               tags=["x"] * m.tags)


# --------------------------------------------------------------------------- #
# 검사
# --------------------------------------------------------------------------- #
def review(doc: Doc, other: Doc | None = None) -> list[Finding]:
    f: list[Finding] = []
    sents = doc.sentences()
    body_sents = [s for s in sents if s not in doc.headings]

    # 1. 첫 2~3문장에 답
    lead = " ".join(body_sents[:3])
    title_words = [w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", doc.title) if len(w) >= 2]
    if title_words and not any(w in lead for w in title_words):
        f.append(Finding("1 첫 문단 답", SUGGEST, "첫 3문장에 제목의 핵심어가 없습니다. 질문에 대한 답을 맨 앞에 두세요."))
    if not re.search(r"\d", lead):
        f.append(Finding("1 첫 문단 답", SUGGEST, "첫 3문장에 숫자가 없습니다. 규모·시기 같은 핵심 수치를 앞에 두면 인용되기 쉽습니다."))

    # 2. 근거 2개 이상, 클릭되는 출처 링크와 날짜
    own = {urllib.parse.urlsplit(u).netloc for _, u in doc.links if "doctoron" in u}
    ext = [(t, u) for t, u in doc.links if urllib.parse.urlsplit(u).netloc not in own]
    if len(ext) < 2:
        plain = _URL_TEXT.findall(doc.text)
        why = f" 주소 {len(plain)}개가 글자로만 적혀 있습니다(클릭 안 됨)." if plain else ""
        f.append(Finding("2 근거·출처", VIOLATION, f"클릭되는 출처 링크가 {len(ext)}개입니다. 2개 이상 필요합니다.{why}"))
    for line in _source_lines(doc.text):
        if not _DATE.search(line):
            f.append(Finding("2 근거·출처", SUGGEST, f"출처에 날짜가 없습니다: {line[:60]}"))

    # 3. 기사 사진·그래픽 복제 금지
    for alt, cap in doc.images:
        both = f"{alt} {cap}"
        if any(w in both for w in CAPTURE_WORDS):
            f.append(Finding("3 기사 복제", VIOLATION, f"기사 캡처로 보이는 이미지: '{both.strip()[:60]}' → 직접 만든 표·그림으로 바꾸세요."))
        elif re.match(r"^(출처|자료)\s*[:：]", cap) and not any(s in cap for s in FREE_IMAGE_SOURCES):
            f.append(Finding("3 기사 복제", CHECK, f"언론사 출처가 달린 이미지: '{cap[:60]}' → 기사 그래픽이면 빼세요."))
    for alt, _ in doc.images:
        if not alt.strip():
            f.append(Finding("형식", SUGGEST, "설명(alt)이 빈 이미지가 있습니다. 검색·AI가 이미지를 이해하도록 한 줄 설명을 넣으세요."))
            break

    # 4. 닥터온 숫자는 허브 확정값만
    for s in sents:
        if "닥터온" in s and re.search(r"\d", s) and not s.startswith("#"):
            f.append(Finding("4 닥터온 숫자", CHECK, f"닥터온 수치가 있습니다(허브 확정값인지 확인): {s[:70]}"))

    # 5. 경쟁사 이름 대신 방식으로
    for name in [n.strip() for n in os.getenv("G6_COMPETITORS", "").split(",") if n.strip()]:
        if name in doc.text:
            f.append(Finding("5 경쟁사", VIOLATION, f"경쟁사 이름 '{name}'이 있습니다. 방식(헤드헌팅·구인 게시판·매칭 플랫폼)으로 바꾸세요."))

    # 6. 두 채널 복붙 금지
    if other is not None:
        same = _overlap(doc, other)
        if len(same) >= 3:
            f.append(Finding("6 복붙", VIOLATION, f"다른 채널 글과 거의 같은 문장 {len(same)}개: " + " / ".join(s[:30] for s in same[:3])))
        elif same:
            f.append(Finding("6 복붙", CHECK, f"다른 채널 글과 거의 같은 문장 {len(same)}개: " + " / ".join(s[:30] for s in same)))

    # 8. 의료 조언 0
    for w in ADVICE_WORDS:
        if w in doc.text:
            f.append(Finding("8 의료 조언", CHECK, f"의료 조언으로 읽힐 수 있는 표현 '{w}'"))

    # 사람 확인: 직함 · 입장 · 법률 문구
    people: dict[str, set[str]] = {}
    for name, title in _NAME_TITLE.findall(doc.text):
        people.setdefault(name, set()).add(title)
    for title, name in _TITLE_NAME.findall(doc.text):
        people.setdefault(name, set()).add(title)
    for name, titles in sorted(people.items()):
        if name in _NOT_NAMES:
            continue
        if len(titles) > 1:
            f.append(Finding("사실 확인", CHECK, f"'{name}' 직함이 글 안에서 다릅니다({' / '.join(sorted(titles))}) — 원문과 대조하세요."))
        else:
            f.append(Finding("사실 확인", CHECK, f"'{name} {next(iter(titles))}' — 직함을 원문과 대조하세요."))
    stance = [w for w in STANCE_WORDS + CONTROVERSY_TERMS if w in doc.text]
    if stance:
        f.append(Finding("입장(DR-MKT-02)", CHECK, f"입장이 드러나는 표현({', '.join(stance[:5])}) — 팀이 승인한 입장인지 확인하세요."))
    if any(w in doc.text for w in LEGAL_TERMS) and "법률 자문" not in doc.text:
        f.append(Finding("법률 표시", CHECK, "계약·법령 내용이 있습니다. '법률 자문이 아닙니다' 문구와 법령 원문 링크를 넣으세요."))

    # 원고 형식 (타깃 2 × 채널 2)
    if doc.channel == "tistory":
        if sum(1 for h in doc.headings) < 3:
            f.append(Finding("형식", SUGGEST, "티스토리는 H2 소제목 3개 이상을 권장합니다."))
        if doc.tables == 0:
            f.append(Finding("형식", SUGGEST, "티스토리는 비교·수치 표 1개 이상을 권장합니다."))
    if doc.channel == "naver" and len(doc.tags) < 3:
        f.append(Finding("형식", SUGGEST, "네이버는 해시태그 3개 이상을 권장합니다."))
    if not any(re.search(r"자주\s*묻는|FAQ|^Q[.\s]", h) for h in doc.headings) and "자주 묻는" not in doc.text:
        f.append(Finding("형식", SUGGEST, "FAQ(자주 묻는 질문) 섹션이 없습니다."))

    f.append(Finding("7 우리만의 관점", CHECK, "닥터온만의 관점·데이터가 1개 이상 있는지 사람이 확인합니다."))
    return f


def verdict(findings: list[Finding]) -> str:
    v = sum(1 for x in findings if x.level == VIOLATION)
    c = sum(1 for x in findings if x.level == CHECK)
    return f"불합격 · 수정 {v}건 · 사람 확인 {c}건" if v else f"합격(사람 확인 {c}건 후 게시)"


def report_md(doc: Doc, findings: list[Finding]) -> str:
    lines = [f"# G6 자동 검수 — {doc.title or '(제목 없음)'}", "", f"**{verdict(findings)}**", ""]
    for level in (VIOLATION, CHECK, SUGGEST):
        items = [x for x in findings if x.level == level]
        if items:
            lines.append(f"## {level} ({len(items)})")
            lines += [f"- [{x.rule}] {x.message}" for x in items]
            lines.append("")
    return "\n".join(lines)


def _source_lines(text: str) -> list[str]:
    lines = text.splitlines()
    out, on = [], False
    for ln in lines:
        s = ln.strip()
        if re.fullmatch(r"(##\s*)?출처", s):
            on = True
            continue
        if on and s.startswith(("·", "-", "•")):
            out.append(s.lstrip("·-• ").strip())
    return out


# 글마다 같아도 되는 문장 (면책 문구) — 복붙 비교에서 뺀다
_BOILERPLATE = re.compile(r"법률 자문이 아닙니다|전문가와 확인하세요|정보 제공용|닥터온 팀")


def _comparable(doc: Doc) -> list[str]:
    """복붙 비교 대상 문장: 출처 섹션(같은 법령·기사를 인용하는 게 정상)과 면책 문구는 뺀다."""
    body = re.split(r"(?m)^\s*(?:##\s*)?출처\s*$", doc.text, maxsplit=1)[0]
    return [s.strip() for s in _SENT.split(body)
            if len(s.strip()) >= 20 and not _BOILERPLATE.search(s)]


def _overlap(a: Doc, b: Doc, threshold: float = 0.75) -> list[str]:
    bs = _comparable(b)
    out = []
    for s in _comparable(a):
        if any(SequenceMatcher(None, s, t).ratio() >= threshold for t in bs):
            out.append(s)
    return out
