"""닥터온 블로그 GEO 체인 노드 CLI.

서브커맨드:
  sources   등록된 소스와 현재 활성 상태 표시
  keywords  G-R 수집 검색어 목록 표시
  gr        G-R 모범 글 구조 분석 실행 → geo_pipeline/out/gr_YYYY-MM.*
  g0        G0 이슈 트래커 실행 → geo_pipeline/out/g0_YYYY-MM-DD.*

예시:
  python -m pipeline.cli gr                                   # 오프라인 sample 로 즉시 체험
  GR_SOURCES=naver NAVER_CLIENT_ID=... NAVER_CLIENT_SECRET=... python -m pipeline.cli gr
  G0_SOURCES=naver_news NAVER_CLIENT_ID=... NAVER_CLIENT_SECRET=... python -m pipeline.cli g0 --hours 72
"""

from __future__ import annotations

import argparse
from datetime import datetime

from .config import Config
from .export import write_g0_outputs, write_outputs
from .g0 import run_g0
from .gr import run_gr
from .keywords import build_queries
from .models import STATUS_AUTO
from .sources import available_keys
from .sources.news import KST, available_news_keys


def cmd_sources(config: Config, args) -> None:
    active = set(config.enabled_source_keys())
    print("등록된 소스:")
    for key in available_keys():
        mark = "✅ 활성" if key in active else "⚪ 비활성(자격증명/설정 없음)"
        print(f"  - {key:15s} {mark}")
    print(f"\n글 페이지 구조 측정(GR_FETCH_PAGES): {'켜짐' if config.fetch_pages else '꺼짐 → 사람 기록'}")

    g0_active = set(config.enabled_g0_source_keys())
    print("\nG0 이슈 트래커 소스:")
    for key in available_news_keys():
        mark = "✅ 활성" if key in g0_active else "⚪ 비활성(자격증명/설정 없음)"
        print(f"  - {key:15s} {mark}")


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


def cmd_g0(config: Config, args) -> None:
    if args.hours:
        config.g0_window_hours = args.hours
    now = datetime.now(KST)
    articles = run_g0(config, now)
    paths = write_g0_outputs(articles, config.out_dir, now.strftime("%Y-%m-%d"))
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
    g0 = sub.add_parser("g0", help="G0 이슈 트래커 (DR-MKT-01)")
    g0.add_argument("--hours", type=int, help="최근 몇 시간 기사를 볼지 (기본 G0_WINDOW_HOURS=26)")
    g0.set_defaults(func=cmd_g0)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(Config(), args)


if __name__ == "__main__":
    main()
