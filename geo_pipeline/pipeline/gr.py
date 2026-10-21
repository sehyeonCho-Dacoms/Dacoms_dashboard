"""G-R 모범 글 구조 분석 노드 (DR-GEO-12) — 월 1회 · AI+사람.

  검색어 15개(+수식어) → 채널별 상위 N개 목록 → (허용 시) 글 열어 구조 측정
  → 글별 기록(CSV/JSON) + 채널×묶음 형식 요약(Markdown)

출력 요약은 허브의 '원고 형식(타깃 2 × 채널 2)' 표 갱신 근거가 되고,
G5 원고·G6 검수의 형식 체크로 이어진다.
"""

from __future__ import annotations

from .config import Config
from .keywords import build_queries
from .models import STATUS_AUTO, STATUS_ERROR, STATUS_MANUAL, STATUS_ROBOTS, PostRef, StructureRecord
from .sources import BaseSource, RobotsBlocked, get_sources
from .structure import analyze_html, title_patterns


def run_gr(config: Config) -> list[StructureRecord]:
    queries = build_queries(config.with_modifiers)
    records: list[StructureRecord] = []
    seen: set[str] = set()

    for source in get_sources(config):
        print(f"🔎 {source.name}: 검색어 {len(queries)}개 × 상위 {config.top_n}")
        refs = source.collect(queries)
        for ref in refs:
            if ref.url in seen:  # 여러 검색어에 같은 글이 걸리면 첫 검색어로만 기록
                continue
            seen.add(ref.url)
            records.append(measure(source, ref, config))
    return records


def measure(source: BaseSource, ref: PostRef, config: Config) -> StructureRecord:
    rec = StructureRecord.from_ref(ref)
    rec.title_len = len(ref.title)
    rec.title_patterns = title_patterns(ref.title)

    # sample 소스는 로컬 HTML이라 항상 측정한다
    if not config.fetch_pages and source.key != "sample":
        rec.status = STATUS_MANUAL
        return rec
    try:
        html = source.load_page(ref)
    except RobotsBlocked:
        rec.status = STATUS_ROBOTS
        return rec
    except Exception as exc:
        rec.status = STATUS_ERROR
        rec.note = type(exc).__name__
        return rec

    m = analyze_html(html, source.page_url(ref), ref.keyword)
    rec.status = STATUS_AUTO
    rec.lead_chars = m.lead_chars
    rec.lead_has_keyword = m.lead_has_keyword
    rec.lead_has_number = m.lead_has_number
    rec.headings = m.headings
    rec.question_headings = m.question_headings
    rec.body_chars = m.body_chars
    rec.images = m.images
    rec.tables = m.tables
    rec.lists = m.lists
    rec.has_faq = m.has_faq
    rec.external_links = m.external_links
    rec.internal_links = m.internal_links
    rec.tags = m.tags
    if not rec.published and m.published:
        rec.published = m.published
    return rec
