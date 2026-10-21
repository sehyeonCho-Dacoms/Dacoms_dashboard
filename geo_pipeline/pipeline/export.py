"""G-R 산출물 쓰기: 글별 기록(JSON·CSV) + 채널×묶음 형식 요약(Markdown).

CSV는 utf-8-sig(BOM)로 저장해 엑셀·노션 가져오기에서 한글이 깨지지 않게 한다.
요약은 '자동 측정'된 글만 집계하고, 사람 기록이 필요한 건수는 따로 적는다.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from statistics import median

from .models import STATUS_AUTO, StructureRecord

# CSV 열 이름 (허브 '글마다 기록할 항목' 순서)
CSV_COLUMNS: list[tuple[str, str]] = [
    ("channel", "채널"),
    ("group", "묶음"),
    ("keyword", "검색어"),
    ("query", "검색 문자열"),
    ("rank", "순위"),
    ("title", "제목"),
    ("url", "링크"),
    ("published", "발행일"),
    ("source", "수집 경로"),
    ("status", "측정 상태"),
    ("title_len", "제목 글자 수"),
    ("title_patterns", "제목 패턴"),
    ("lead_chars", "첫 3문장 글자 수"),
    ("lead_has_keyword", "첫 3문장 검색어 포함"),
    ("lead_has_number", "첫 3문장 숫자 포함"),
    ("headings", "소제목 수"),
    ("question_headings", "질문형 소제목 수"),
    ("body_chars", "본문 글자 수"),
    ("images", "이미지 수"),
    ("image_kinds", "이미지 종류(사람)"),
    ("tables", "표"),
    ("lists", "목록"),
    ("has_faq", "FAQ"),
    ("external_links", "출처(외부) 링크 수"),
    ("internal_links", "내부 링크 수"),
    ("tags", "태그 수"),
    ("author_profile", "작성자 소개(사람)"),
    ("likes", "공감(사람)"),
    ("comments", "댓글(사람)"),
    ("note", "비고"),
]

CHANNEL_LABEL = {"naver": "네이버 블로그", "tistory": "티스토리"}


def write_outputs(records: list[StructureRecord], out_dir: Path, period: str | None = None) -> dict[str, Path]:
    period = period or date.today().strftime("%Y-%m")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": out_dir / f"gr_{period}.json",
        "csv": out_dir / f"gr_{period}.csv",
        "summary": out_dir / f"gr_{period}_summary.md",
    }
    rows = [r.to_dict() for r in records]
    paths["json"].write_text(
        json.dumps({"period": period, "count": len(rows), "records": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with paths["csv"].open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([label for _, label in CSV_COLUMNS])
        for r in rows:
            w.writerow([_cell(r[key]) for key, _ in CSV_COLUMNS])
    paths["summary"].write_text(build_summary(records, period), encoding="utf-8")
    return paths


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "O" if v else "X"
    if isinstance(v, list):
        return "·".join(v)
    return str(v)


# --------------------------------------------------------------------------- #
# 요약
# --------------------------------------------------------------------------- #
def summarize(records: list[StructureRecord]) -> list[dict]:
    """채널 × 묶음별 구조 지표 집계 (자동 측정분만)."""
    keys = sorted({(r.channel, r.group) for r in records})
    out = []
    for channel, group in keys:
        rs = [r for r in records if r.channel == channel and r.group == group]
        auto = [r for r in rs if r.status == STATUS_AUTO]
        pats = Counter(p for r in rs for p in r.title_patterns)
        row = {
            "channel": channel,
            "group": group,
            "posts": len(rs),
            "measured": len(auto),
            "title_len_median": _med([r.title_len for r in rs]),
            "title_patterns_top": [f"{p} {n}" for p, n in pats.most_common(3)],
        }
        if auto:
            row.update(
                body_chars_median=_med([r.body_chars for r in auto]),
                headings_avg=_avg([r.headings for r in auto]),
                question_heading_share=_share(auto, lambda r: (r.question_headings or 0) > 0),
                lead_keyword_share=_share(auto, lambda r: r.lead_has_keyword),
                images_avg=_avg([r.images for r in auto]),
                table_share=_share(auto, lambda r: (r.tables or 0) > 0),
                list_share=_share(auto, lambda r: (r.lists or 0) > 0),
                faq_share=_share(auto, lambda r: r.has_faq),
                external_links_avg=_avg([r.external_links for r in auto]),
                tags_avg=_avg([r.tags for r in auto]),
            )
        out.append(row)
    return out


def build_summary(records: list[StructureRecord], period: str) -> str:
    rows = summarize(records)
    manual = sum(1 for r in records if r.status != STATUS_AUTO)
    lines = [
        f"# G-R 모범 글 구조 분석 요약 — {period}",
        "",
        f"- 기록한 글: {len(records)}개 · 자동 측정 {len(records) - manual}개 · 사람 기록 필요 {manual}개",
        "- 본문은 저장하지 않았습니다. 지표와 링크만 남겼습니다.",
        "- '첫 3문장 검색어 포함'은 답이 있는지의 힌트일 뿐입니다. 실제로 답하는지는 사람이 확인합니다.",
        "",
        "| 채널 | 묶음 | 글 | 측정 | 제목 글자(중앙) | 제목 패턴 상위 | 본문 글자(중앙) | 소제목(평균) "
        "| 질문형 소제목 있는 글 | 첫 3문장 검색어 | 이미지(평균) | 표 | 목록 | FAQ | 출처 링크(평균) | 태그(평균) |",
        "| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        g = r.get
        lines.append(
            f"| {CHANNEL_LABEL.get(r['channel'], r['channel'])} | {r['group']} | {r['posts']} | {r['measured']} "
            f"| {_fmt(g('title_len_median'))} | {', '.join(r['title_patterns_top']) or '—'} "
            f"| {_fmt(g('body_chars_median'))} | {_fmt(g('headings_avg'))} | {_pct(g('question_heading_share'))} "
            f"| {_pct(g('lead_keyword_share'))} | {_fmt(g('images_avg'))} | {_pct(g('table_share'))} "
            f"| {_pct(g('list_share'))} | {_pct(g('faq_share'))} | {_fmt(g('external_links_avg'))} "
            f"| {_fmt(g('tags_avg'))} |"
        )
    lines += [
        "",
        "## 다음 할 일 (사람)",
        "",
        "- 사람 기록이 필요한 글은 CSV에서 '측정 상태'로 걸러 열어 보고, 빈 칸(이미지 종류·작성자 소개·공감·댓글)을 채웁니다.",
        "- 이 표를 보고 허브의 '원고 형식(타깃 2 × 채널 2)' 표를 갱신합니다 → G5 원고 가이드, G6 검수 형식 체크.",
        "",
    ]
    return "\n".join(lines)


def _med(xs):
    xs = [x for x in xs if x is not None]
    return median(xs) if xs else None


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def _share(rs, pred) -> float:
    return sum(1 for r in rs if pred(r)) / len(rs)


def _fmt(v) -> str:
    if v is None:
        return "—"
    return f"{v:g}" if isinstance(v, float) else str(v)


def _pct(v) -> str:
    return "—" if v is None else f"{round(v * 100)}%"
