"""닥터온 블로그 GEO 체인 노드 CLI.

서브커맨드:
  sources   등록된 소스와 현재 활성 상태 표시
  keywords  G-R 수집 검색어 목록 표시
  gr        G-R 모범 글 구조 분석 실행 → geo_pipeline/out/gr_YYYY-MM.*

예시:
  python -m pipeline.cli gr                                   # 오프라인 sample 로 즉시 체험
  GR_SOURCES=naver NAVER_CLIENT_ID=... NAVER_CLIENT_SECRET=... python -m pipeline.cli gr
"""

from __future__ import annotations

import argparse

from .config import Config
from .export import write_outputs
from .gr import run_gr
from .keywords import build_queries
from .models import STATUS_AUTO
from .sources import available_keys


def cmd_sources(config: Config, args) -> None:
    active = set(config.enabled_source_keys())
    print("등록된 소스:")
    for key in available_keys():
        mark = "✅ 활성" if key in active else "⚪ 비활성(자격증명/설정 없음)"
        print(f"  - {key:15s} {mark}")
    print(f"\n글 페이지 구조 측정(GR_FETCH_PAGES): {'켜짐' if config.fetch_pages else '꺼짐 → 사람 기록'}")


def cmd_keywords(config: Config, args) -> None:
    queries = build_queries(config.with_modifiers)
    for q in queries:
        print(f"  [{q.group}] {q.query}")
    print(f"\n총 {len(queries)}개 (수식어 2차 {'포함' if config.with_modifiers else '미포함'})")


def cmd_gr(config: Config, args) -> None:
    records = run_gr(config)
    paths = write_outputs(records, config.out_dir, args.period)
    auto = sum(1 for r in records if r.status == STATUS_AUTO)
    print(f"📤 기록 {len(records)}개 (자동 측정 {auto} · 사람 기록 {len(records) - auto})")
    for kind, path in paths.items():
        print(f"   {kind:8s}→ {path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="geo", description="닥터온 블로그 GEO 체인 노드")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("sources", help="소스 활성 상태 표시").set_defaults(func=cmd_sources)
    sub.add_parser("keywords", help="G-R 검색어 목록").set_defaults(func=cmd_keywords)
    gr = sub.add_parser("gr", help="G-R 모범 글 구조 분석 (DR-GEO-12)")
    gr.add_argument("--period", help="산출물 이름에 쓸 기간 (기본: 이번 달 YYYY-MM)")
    gr.set_defaults(func=cmd_gr)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(Config(), args)


if __name__ == "__main__":
    main()
