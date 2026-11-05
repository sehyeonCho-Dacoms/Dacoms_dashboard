"""닥터온 블로그 GEO 체인 노드 CLI.

서브커맨드:
  sources   등록된 소스와 현재 활성 상태 표시
  keywords  G-R 수집 검색어 목록 표시
  gr        G-R 모범 글 구조 분석 실행 → geo_pipeline/out/gr_YYYY-MM.*
  g0        G0 이슈 트래커 실행 → geo_pipeline/out/g0_YYYY-MM-DD.*
  review    G6 자동 검수 (원고 .md 또는 게시된 글 URL, --other 로 다른 채널 글과 복붙 비교)
  build     원고 .md → 채널별 붙여 넣기 완성본(HTML) + 검수 보고서 → geo_pipeline/out/drafts/
  g3        'G2 오늘의 후보' 점수 1·2등 자동 선택 → 체인 DB 글 행(근거수집). 여기서 웅서(G4~)에게 넘어감

예시:
  python -m pipeline.cli gr                                   # 오프라인 sample 로 즉시 체험
  GR_SOURCES=naver NAVER_CLIENT_ID=... NAVER_CLIENT_SECRET=... python -m pipeline.cli gr
  G0_SOURCES=naver_news NAVER_CLIENT_ID=... NAVER_CLIENT_SECRET=... python -m pipeline.cli g0 --hours 72
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

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
    stats: dict = {}
    articles = run_g0(config, now, stats)
    paths = write_g0_outputs(articles, config.out_dir, now.strftime("%Y-%m-%d"), stats)
    for kind, path in paths.items():
        print(f"   {kind:8s}→ {path}")
    _g2(config, articles, now)
    if args.notion:
        from . import notion_g0

        print(notion_g0.push(articles, now))


def _g2(config: Config, articles, now) -> None:
    """G2 흥미도 점수 (준칙 v1). 체인 DB는 읽기만 하고(글 쓴 질문·14일 안 같은 질문), 후보는 'G2 오늘의 후보' DB에."""
    import json

    from . import g2, notion_g0

    try:
        chain = notion_g0.chain_questions(now)
    except Exception as exc:   # 노션을 못 읽어도 채점은 한다 (상록 슬롯·⑥만 덜 정확)
        print(f"   ⚠️  체인 DB 읽기 실패({getattr(exc, 'code', type(exc).__name__)}) → 글 쓴 질문 정보 없이 채점")
        chain = None
    written, recent = chain if chain else (set(), {})
    from . import g1q   # D-056: 노션 질문 은행 값 반영 + 재고 5개 미만이면 '근거 필요' 질문 자동 검수·승격
    for ln in g1q.run(config, now, written if chain else None, dry_run=os.getenv("G1Q_DRY") == "1"):
        print(ln)
    scores, top, slots = g2.run_g2(articles, now, written, recent)
    day = now.strftime("%Y-%m-%d")
    md = config.out_dir / f"g2_{day}.md"
    md.write_text(g2.summary_md(scores, top, slots, day), encoding="utf-8")
    (config.out_dir / f"g2_{day}.json").write_text(json.dumps({
        "day": day, "cutoff": g2.CUTOFF,
        "candidates": [{"id": s.article.id, "title": s.article.title, "url": s.article.url, "total": s.total,
                        "abcdef": [s.a, s.b, s.c, s.d, s.e, s.f], "target": s.target,
                        "gq": s.gq.gq if s.gq else None, "channel": s.channel, "marks": s.marks} for s in top],
        "evergreen": [{"gq": q.gq, "question": q.text, "target": q.target, "channel": q.channel} for q in slots],
        "scored": [g2.line(s) for s in scores],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"🎯 G2: 채점 {len(scores)}건 · {g2.CUTOFF}점 이상 후보 {len(top)}건 · 상록 슬롯 {len(slots)}건 → {md}")
    print(g2.stock_line(written if chain else None))   # D-036 재고 5개 미만이면 🔔
    print(notion_g0.push_candidates(top, slots, now))   # G3 담당자는 노션 'G2 오늘의 후보'에서 고른다


def cmd_g1q(config: Config, args) -> None:
    """G1-Q 질문 검수만 따로 (미리 보기·수동 실행용). 평소에는 G0 안에서 G2 직전에 돈다."""
    from . import g1q, notion_g0

    now = datetime.now(KST)
    try:
        chain = notion_g0.chain_questions(now)
    except Exception as exc:
        print(f"❌ {g1q.TAG}: 체인 DB 읽기 실패({getattr(exc, 'code', type(exc).__name__)})")
        return
    for ln in g1q.run(config, now, chain[0] if chain else None, dry_run=args.dry_run):
        print(ln)
    from . import g2

    print(g2.stock_line(chain[0] if chain else None))


def _load_doc(target: str):
    from . import _http, review
    from .draft import load
    from .sources.naver import to_mobile_url

    if target.startswith("http"):
        url = to_mobile_url(target.split("?")[0])
        html = _http.get_text(url, headers={"User-Agent": "Mozilla/5.0"})
        return review.from_html(html, url)
    return review.from_draft(load(Path(target)))


def cmd_review(config: Config, args) -> None:
    from . import review

    doc = _load_doc(args.target)
    other = _load_doc(args.other) if args.other else None
    findings = review.review(doc, other)
    print(review.report_md(doc, findings))


def cmd_build(config: Config, args) -> None:
    from . import render, review
    from .draft import load

    src = Path(args.draft)
    d = load(src)
    other = _load_doc(args.other) if args.other else None
    out = config.out_dir / "drafts" / src.stem
    out.mkdir(parents=True, exist_ok=True)
    (out / "tistory.html").write_text(render.to_tistory(d), encoding="utf-8")
    (out / "naver.html").write_text(render.to_naver(d), encoding="utf-8")
    findings = review.review(review.from_draft(d), other)
    (out / "review.md").write_text(review.report_md(review.from_draft(d), findings), encoding="utf-8")

    report = review.report_md(review.from_draft(d), findings)
    if args.images:
        from . import images

        made = images.render(d, out / "images")
        print(f"   🖼  이미지 {len(made)}장 → {out / 'images'}/ ({', '.join(i.file for i in made)})")
    print(f"📝 {d.title} → {out}/ (tistory.html · naver.html · review.md)")
    print(f"   G6 자동 검수: {review.verdict(findings)}")
    if args.notion:
        from . import notion

        url = notion.push(d, (out / "tistory.html").read_text(encoding="utf-8"),
                          (out / "naver.html").read_text(encoding="utf-8"), report, review.verdict(findings))
        print(f"   노션: {url}" if url else "   노션: NOTION_TOKEN 이 없어 건너뜀")


def cmd_photo(config: Config, args) -> None:
    from . import images
    for q in args.queries:
        print(f"### {q}")
        found = images.find_photo(q, limit=args.limit) or []
        if not found:
            print("(CC0 후보 없음)\n")
        for i, ph in enumerate(found, 1):
            print(f"{i}. {ph['title']} — {ph['license']} · {ph['artist']}\n   {ph['page']}")
            print("   원고 머리말에 붙여 넣기:")
            for k in ("url", "page", "license", "artist"):
                print(f"   photo_{k}: {ph[k]}")
        print()


def cmd_photo_sync(config: Config, args) -> None:
    from . import photos
    print("\n".join(photos.sync(dry_run=args.dry_run, replace=args.replace)))


def cmd_g3(config: Config, args) -> None:
    from . import g1q, g3

    g1q.refresh()   # 행 설명의 답 준비도를 노션 값으로 (D-056 승격 반영, 실패하면 코드 사본)
    print("\n".join(g3.run(datetime.now(KST), dry_run=args.dry_run, day=args.day)))


def cmd_g8(config: Config, args) -> None:
    from datetime import date

    from . import g8
    today = date.fromisoformat(args.today) if args.today else None
    print("\n".join(g8.run(datetime.now(KST), dry_run=args.dry_run, today=today)))


def cmd_notify(config: Config, args) -> None:
    """로그의 ⛔(❌)·⏸ 줄을 슬랙으로 (D-046). --daily 면 문제가 없을 때 ✅ 하루 요약(각 로그 첫 줄)을 보낸다.
    웹훅이 없거나 보내다 실패해도 워크플로를 깨지 않는다."""
    from pathlib import Path

    from . import notify

    texts = [Path(f).read_text(encoding="utf-8") for f in args.log if Path(f).exists()]
    summary = [next((ln for ln in t.splitlines() if ln.strip()), "") for t in texts]
    try:
        print(notify.send(args.title, "\n".join(texts), args.run_url or "", daily=args.daily, summary=summary))
    except Exception as exc:   # 알림 실패가 본 작업 결과를 가리지 않게
        print(f"   ⚠️ 슬랙 전송 실패: {getattr(exc, 'code', type(exc).__name__)}")


def cmd_notion_check(config: Config, args) -> None:
    from . import notion

    print(notion.check())


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
    g0.add_argument("--notion", action="store_true", help="거름망 통과 기사를 노션 '블로그 GEO 체인' DB에 '질문선택' 행으로 올림")
    g0.set_defaults(func=cmd_g0)
    rv = sub.add_parser("review", help="G6 자동 검수 (원고 .md 또는 게시 글 URL)")
    rv.add_argument("target", help="원고 .md 경로 또는 게시된 글 URL")
    rv.add_argument("--other", help="다른 채널 글(원고 또는 URL) — 복붙 비교")
    rv.set_defaults(func=cmd_review)
    bd = sub.add_parser("build", help="원고 .md → 티스토리·네이버 완성본 + 검수 보고서")
    bd.add_argument("draft", help="원고 .md 경로")
    bd.add_argument("--other", help="다른 채널 글(원고 또는 URL) — 복붙 비교")
    bd.add_argument("--images", action="store_true", help="블로그 이미지 4장 생성 (Playwright·Chromium 필요)")
    bd.add_argument("--notion", action="store_true", help="노션 '블로그 GEO 체인' DB에 행 만들기 (NOTION_TOKEN 필요)")
    bd.set_defaults(func=cmd_build)
    ph = sub.add_parser("photo", help="사진 후보 찾기 (Pixabay 키가 있으면 Pixabay, 없으면 Wikimedia CC0)")
    ph.add_argument("queries", nargs="+", help="영어 검색어 (여러 개 가능)")
    ph.add_argument("--limit", type=int, default=3)
    ph.set_defaults(func=cmd_photo)
    ps = sub.add_parser("photo-sync", help="노션 원고 행마다 글 주제에 맞는 CC0 사진 후보를 자동으로 붙임")
    ps.add_argument("--dry-run", action="store_true", help="노션에 쓰지 않고 결과만 출력")
    ps.add_argument("--replace", action="store_true", help="이미 붙은 사진 섹션을 지우고 다시 찾음")
    ps.set_defaults(func=cmd_photo_sync)
    g3p = sub.add_parser("g3", help="G3: 'G2 오늘의 후보' 점수 1·2등 자동 선택 → 체인 DB 글 행(근거수집, 담당 웅서)")
    g3p.add_argument("--dry-run", action="store_true", help="노션에 쓰지 않고 만들 행만 보기")
    g3p.add_argument("--day", help="후보 날짜 YYYY-MM-DD (기본: 오늘)")
    g3p.set_defaults(func=cmd_g3)
    g1p = sub.add_parser("g1q", help="G1-Q: 질문 은행 '근거 필요' 질문을 검색 근거로 검수해 '바로 가능'으로 올림 (D-056)")
    g1p.add_argument("--dry-run", action="store_true", help="노션에 쓰지 않고 판정만 보기")
    g1p.set_defaults(func=cmd_g1q)
    g8p = sub.add_parser("g8", help="G8: 게시 글 D+3·7·30 색인·조회수 측정 → 체인 DB (네이버 검색 API · Search Console · GA4)")
    g8p.add_argument("--dry-run", action="store_true", help="노션에 쓰지 않고 잴 글·결과만 보기")
    g8p.add_argument("--today", help="기준일 YYYY-MM-DD (기본: 오늘, 시험용)")
    g8p.set_defaults(func=cmd_g8)
    nt = sub.add_parser("notify", help="로그의 ⛔·⏸ 줄을 슬랙으로 보냄, --daily 면 문제없을 때 ✅ 요약 (SLACK_WEBHOOK_URL, 없으면 건너뜀)")
    nt.add_argument("--log", nargs="+", required=True, help="읽을 로그 파일")
    nt.add_argument("--title", default="블로그 GEO 체인 알림")
    nt.add_argument("--run-url", help="GitHub Actions 실행 주소")
    nt.add_argument("--daily", action="store_true", help="하루 1번 도는 실행: 문제가 없어도 ✅ 요약을 보냄 (D-046)")
    nt.set_defaults(func=cmd_notify)
    sub.add_parser("notion-check", help="NOTION_TOKEN 으로 '블로그 GEO 체인' DB 접속 확인").set_defaults(func=cmd_notion_check)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(Config(), args)


if __name__ == "__main__":
    main()
