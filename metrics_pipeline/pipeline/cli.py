"""카드뉴스 성과 수집 파이프라인 CLI.

서브커맨드:
  sources   등록된 소스와 현재 활성 상태 표시
  collect   활성 소스에서 성과 수집 → 스토어에 증분 병합 저장
  export    스토어를 읽어 metrics-analyzer용 CSV 생성
  run       collect + export 를 한 번에

예시:
  python -m pipeline.cli run                 # 오프라인 sample 로 즉시 체험
  METRICS_SOURCES=instagram IG_ACCESS_TOKEN=... IG_BUSINESS_ACCOUNT_ID=... \
    python -m pipeline.cli run
"""

from __future__ import annotations

import argparse

from .collect import collect
from .config import Config
from .export import unregistered_post_ids, write_metrics_csv
from .sources import available_keys
from .store import load_metrics, merge, save_metrics


def cmd_sources(config: Config, args) -> None:
    active = set(config.enabled_source_keys())
    print("등록된 소스:")
    for key in available_keys():
        mark = "✅ 활성" if key in active else "⚪ 비활성(자격증명 없음)"
        print(f"  - {key:10s} {mark}")
    print(f"\n조회 기간: 최근 {config.ig_lookback_days}일")
    print(f"레지스트리 경로: {config.post_registry_path} (존재: {config.post_registry_path.exists()})")


def cmd_collect(config: Config, args) -> list:
    print(f"🔎 수집 시작 (소스: {', '.join(config.enabled_source_keys())})")
    incoming, _ = collect(config)
    existing = load_metrics(config.store_path)
    merged = merge(existing, incoming)
    save_metrics(config.store_path, merged)
    print(f"💾 스토어 저장: {len(merged)}건 (신규 수집 {len(incoming)}건) → {config.store_path}")
    return merged


def cmd_export(config: Config, args) -> None:
    existing = load_metrics(config.store_path)
    if not existing:
        print("⚠️  스토어가 비어 있습니다. 먼저 collect 를 실행하세요.")
        return
    write_metrics_csv(config.metrics_csv, existing)
    print(f"📤 성과 CSV 생성 → {config.metrics_csv} ({len(existing)}건)")
    unreg = unregistered_post_ids(existing)
    if unreg:
        print(f"⚠️  post_registry.csv 미등록 {len(unreg)}건 — topic/sport_category/format 비어 있음:")
        for pid in unreg[:10]:
            print(f"     - {pid}")


def cmd_run(config: Config, args) -> None:
    merged = cmd_collect(config, args)
    write_metrics_csv(config.metrics_csv, merged)
    unreg = unregistered_post_ids(merged)
    print(f"📤 성과 CSV 생성 → {config.metrics_csv} ({len(merged)}건, 미등록 {len(unreg)}건)")
    print("✅ 완료. metrics-analyzer 에이전트가 이 CSV를 읽어 분석할 수 있습니다.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="metrics", description="카드뉴스 성과 수집 파이프라인")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("sources", help="소스 활성 상태 표시").set_defaults(func=cmd_sources)
    sub.add_parser("collect", help="수집 → 스토어 저장").set_defaults(func=cmd_collect)
    sub.add_parser("export", help="스토어 → CSV").set_defaults(func=cmd_export)
    sub.add_parser("run", help="collect + export 일괄 실행").set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(Config(), args)


if __name__ == "__main__":
    main()
