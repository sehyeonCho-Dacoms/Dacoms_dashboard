"""원고 → 채널별 붙여 넣기용 완성본 (G5 출력 · G7 사람 게시 직전).

- 티스토리: H2/H3 · 표 · 출처 링크 · FAQ (원고 형식 '의사 × 티스토리')
- 네이버:   큰 글씨 굵은 소제목 · 짧은 문단 · 끝에 해시태그 (원고 형식 '의사 × 네이버')
  스마트에디터에 HTML을 붙여 넣으면 굵게·링크·표는 대체로 유지되지만 글자 크기는
  빠질 수 있다. 소제목은 붙여 넣은 뒤 에디터의 '소제목' 블록으로 바꾸는 것을 권한다.

자동 게시는 하지 않는다(체인 v1: G7 게시 = 사람). 두 플랫폼 모두 공식 글쓰기 API가 없다.
"""

from __future__ import annotations

import html
import re

from .draft import Block, Draft

_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def inline(text: str) -> str:
    """인라인 마크다운(링크·굵게) → HTML. 나머지는 이스케이프."""
    out, pos = [], 0
    for m in _LINK.finditer(text):
        out.append(_bold(html.escape(text[pos:m.start()])))
        out.append(f'<a href="{html.escape(m.group(2), quote=True)}" target="_blank" rel="noopener">'
                   f"{_bold(html.escape(m.group(1)))}</a>")
        pos = m.end()
    out.append(_bold(html.escape(text[pos:])))
    return "".join(out)


def _bold(escaped: str) -> str:
    return _BOLD.sub(r"<b>\1</b>", escaped)


def _table(b: Block) -> str:
    if not b.rows:
        return ""
    head, *body = b.rows
    th = "".join(f"<th>{inline(c)}</th>" for c in head)
    trs = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def _image(b: Block) -> str:
    cap = f"<figcaption>{html.escape(b.caption)}</figcaption>" if b.caption else ""
    return (f'<figure><img src="{html.escape(b.src, quote=True)}" alt="{html.escape(b.alt, quote=True)}">'
            f"{cap}</figure>")


def to_tistory(d: Draft) -> str:
    parts = []
    for b in d.blocks:
        if b.kind == "heading":
            parts.append(f"<h{b.level}>{inline(b.text)}</h{b.level}>")
        elif b.kind == "para":
            parts.append(f"<p>{inline(b.text)}</p>")
        elif b.kind == "table":
            parts.append(_table(b))
        elif b.kind == "image":
            parts.append(_image(b))
        elif b.kind == "quote":
            parts.append(f"<blockquote>{inline(b.text)}</blockquote>")
        elif b.kind == "list":
            parts.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in b.items) + "</ul>")
    return "\n".join(parts) + "\n"


def to_naver(d: Draft) -> str:
    """네이버 붙여 넣기용. 문단은 문장 단위로 줄을 나눠 모바일에서 짧게 보이게 한다."""
    parts = []
    for b in d.blocks:
        if b.kind == "heading":
            size = "24px" if b.level == 2 else "19px"
            parts.append(f'<p><br></p><p><span style="font-size:{size}"><b>{inline(b.text)}</b></span></p>')
        elif b.kind == "para":
            sentences = re.split(r"(?<=[.?!])\s+", b.text)
            parts.append("".join(f"<p>{inline(s)}</p>" for s in sentences if s) + "<p><br></p>")
        elif b.kind == "table":
            parts.append(_table(b))
        elif b.kind == "image":
            parts.append(_image(b))
        elif b.kind == "quote":
            parts.append(f"<blockquote>{inline(b.text)}</blockquote>")
        elif b.kind == "list":
            parts.append("".join(f"<p>☑ {inline(i)}</p>" for i in b.items))
    if d.tags:
        parts.append("<p>" + " ".join(f"#{html.escape(t)}" for t in d.tags) + "</p>")
    return "\n".join(parts) + "\n"
