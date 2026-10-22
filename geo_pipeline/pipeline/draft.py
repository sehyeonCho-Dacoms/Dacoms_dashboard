"""원고(G5) 형식 — 머리말 + 단순 마크다운 → 블록 목록.

원고 한 개를 쓰고, 채널별 완성본(render.py)과 검수(review.py)가 같은 블록을 쓴다.

    ---
    title: 의사 헤드헌팅과 매칭 플랫폼은 뭐가 달라?
    channel: tistory            # tistory | naver
    target: 의사                 # 의사 | 반의사
    question: GQ-6
    tags: 의사이직, 헤드헌팅
    ---
    첫 문단 (첫 2~3문장에 답)

    ## 소제목
    본문, [링크 글자](https://...), **굵게**
    | 표 | 머리 |
    | --- | --- |
    | 칸 | 칸 |
    ![이미지 설명(alt)](https://... "캡션")
    > 인용
    - 목록
    ### Q. 자주 묻는 질문

외부 의존성 없이 위 문법만 지원한다(원고 작성 규칙을 좁게 두는 편이 검수에 유리하다).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_IMAGE = re.compile(r'^!\[([^\]]*)\]\((\S+?)(?:\s+"([^"]*)")?\)$')


@dataclass
class Block:
    kind: str                      # heading | para | table | image | quote | list
    text: str = ""                 # heading·para·quote 원문(인라인 마크다운 포함)
    level: int = 0                 # heading 2·3
    rows: list[list[str]] = field(default_factory=list)   # table (첫 행이 머리)
    items: list[str] = field(default_factory=list)        # list
    alt: str = ""                  # image
    src: str = ""
    caption: str = ""


@dataclass
class Draft:
    meta: dict[str, str]
    blocks: list[Block]

    @property
    def title(self) -> str:
        return self.meta.get("title", "")

    @property
    def channel(self) -> str:
        return self.meta.get("channel", "")

    @property
    def tags(self) -> list[str]:
        return [t.strip().lstrip("#") for t in self.meta.get("tags", "").split(",") if t.strip()]

    def plain_text(self) -> str:
        """검수용 평문 (마크다운 기호 제거, 표·목록 포함)."""
        out: list[str] = []
        for b in self.blocks:
            if b.kind in ("heading", "para", "quote"):
                out.append(strip_inline(b.text))
            elif b.kind == "table":
                out.extend(" | ".join(strip_inline(c) for c in r) for r in b.rows)
            elif b.kind == "list":
                out.extend(strip_inline(i) for i in b.items)
        return "\n".join(out)

    def links(self) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for b in self.blocks:
            for t in [b.text, *b.items, *(c for r in b.rows for c in r)]:
                found.extend(_LINK.findall(t))
        return found


def strip_inline(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    return text.replace("**", "").strip()


def load(path: Path) -> Draft:
    return parse(path.read_text(encoding="utf-8"))


def parse(src: str) -> Draft:
    meta: dict[str, str] = {}
    lines = src.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
        for ln in lines[1:end]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                k = k.strip()   # title 은 그대로, 나머지는 '  # 설명' 주석만 제거
                meta[k] = v.strip() if k == "title" else re.split(r"\s+#\s", v, maxsplit=1)[0].strip()
        lines = lines[end + 1:]

    blocks: list[Block] = []
    para: list[str] = []

    def flush() -> None:
        if para:
            blocks.append(Block("para", " ".join(s.strip() for s in para)))
            para.clear()

    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        s = ln.strip()
        if not s:
            flush()
        elif s.startswith("### ") or s.startswith("## "):
            flush()
            level = 3 if s.startswith("### ") else 2
            blocks.append(Block("heading", s[level + 1:].strip(), level=level))
        elif s.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            blocks.append(Block("table", rows=rows))
            continue
        elif m := _IMAGE.match(s):
            flush()
            blocks.append(Block("image", alt=m.group(1), src=m.group(2), caption=m.group(3) or ""))
        elif s.startswith("> "):
            flush()
            blocks.append(Block("quote", s[2:].strip()))
        elif s.startswith("- "):
            flush()
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:].strip())
                i += 1
            blocks.append(Block("list", items=items))
            continue
        else:
            para.append(s)
        i += 1
    flush()
    return Draft(meta, blocks)
