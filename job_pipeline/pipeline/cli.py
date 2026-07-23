"""드래프트온 채용 수집 파이프라인 CLI.

서브커맨드:
  sources   등록된 소스와 현재 활성 상태 표시
  collect   활성 소스에서 공고 수집 → 스코어링 → 스토어에 증분 병합 저장
  export    스토어를 읽어 대시보드용 dashboard.json 생성
  run       collect + export 를 한 번에 (권장: 크론으로 주기 실행)

예시:
  python -m pipeline.cli run                 # 오프라인 sample 로 즉시 체험
  JOB_SOURCES=saramin SARAMIN_ACCESS_KEY=... python -m pipeline.cli run
"""

from __future__ import annotations

import argparse

from .collect import collect
from .config import Config
from .export import write_dashboard_json
from .scoring import build_leads, score_jobs
from .sources import available_keys
from .store import load_jobs, merge, prev_open_counts, save_jobs


def cmd_sources(config: Config, args) -> None:
    active = set(config.enabled_source_keys())
    print("등록된 소스:")
    for key in available_keys():
        mark = "✅ 활성" if key in active else "⚪ 비활성(자격증명/설정 없음)"
        print(f"  - {key:10s} {mark}")
    print(f"\n키워드: {', '.join(config.keywords)}")


def cmd_collect(config: Config, args) -> list:
    print(f"🔎 수집 시작 (소스: {', '.join(config.enabled_source_keys())})")
    incoming, _ = collect(config)
    incoming = score_jobs(incoming)

    existing = load_jobs(config.store_path)
    merged = merge(existing, incoming)
    save_jobs(config.store_path, merged)
    print(f"💾 스토어 저장: {len(merged)}건 (신규 수집 {len(incoming)}건) → {config.store_path}")
    return merged


def cmd_export(config: Config, args) -> None:
    existing = load_jobs(config.store_path)
    if not existing:
        print("⚠️  스토어가 비어 있습니다. 먼저 collect 를 실행하세요.")
        return
    existing = score_jobs(existing)  # 스토어 로드분 재채점(가중치 변경 반영)
    leads = build_leads(existing, prev_open=prev_open_counts([]))
    out = config.dashboard_json
    payload = write_dashboard_json(out, existing, leads)
    k = payload["kpis"]
    print(f"📤 대시보드 데이터 생성 → {out}")
    print(f"   수집 {k['collected']}건 · 업로드적합 {k['uploadReady']}건 · "
          f"Hot리드 {k['hotLeads']}곳 · 파이프라인 {k['pipelineValueLabel']}")


def cmd_run(config: Config, args) -> None:
    prev = load_jobs(config.store_path)
    prev_counts = prev_open_counts(prev)

    merged = cmd_collect(config, args)
    merged = score_jobs(merged)
    leads = build_leads(merged, prev_open=prev_counts)
    payload = write_dashboard_json(config.dashboard_json, merged, leads)
    k = payload["kpis"]
    print(f"📤 대시보드 데이터 생성 → {config.dashboard_json}")
    print(f"   수집 {k['collected']}건 · 업로드적합 {k['uploadReady']}건 · "
          f"Hot리드 {k['hotLeads']}곳 · 파이프라인 {k['pipelineValueLabel']}")
    print("✅ 완료. dashboard.html 을 로컬 서버로 열면 실데이터가 반영됩니다.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jobs", description="드래프트온 채용 수집 파이프라인")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("sources", help="소스 활성 상태 표시").set_defaults(func=cmd_sources)
    sub.add_parser("collect", help="수집 → 스코어링 → 스토어 저장").set_defaults(func=cmd_collect)
    sub.add_parser("export", help="스토어 → 대시보드 JSON").set_defaults(func=cmd_export)
    sub.add_parser("run", help="collect + export 일괄 실행").set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(Config(), args)


if __name__ == "__main__":
    main()
