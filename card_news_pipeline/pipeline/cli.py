"""카드뉴스 파이프라인 CLI.

서브커맨드:
  init        입력/초안 시트(또는 CSV) 헤더 생성 + 로컬 샘플 주제 시드
  generate    주제 시트를 읽어 Claude로 P.D.A. 5앵글 카피 생성 → 초안 시트 기입
  export      승인된 카피만 모아 피그마 플러그인용 JSON으로 내보내기
  render      승인된 카피를 OpenAI 이미지 + Playwright로 카드 PNG 렌더링
  run         generate → (검토/승인 후) export + render 안내를 포함한 상태 출력
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Config
from .copywriter import generate_angles
from .models import CopyAngle
from .sheets import get_backend


def _apply_common(config: Config, args) -> Config:
    if getattr(args, "backend", None):
        config.backend = args.backend
    return config


# --------------------------------------------------------------------------- #
def cmd_init(config: Config, args) -> None:
    backend = get_backend(config)
    backend.ensure_headers()
    print(f"✅ 헤더 준비 완료 (backend={config.backend})")

    if config.backend == "local" and args.seed:
        from .sheets import LocalCsvBackend

        assert isinstance(backend, LocalCsvBackend)
        topics = backend._read_rows(backend.topic_path)
        if len(topics) <= 1:  # 헤더만 있으면 샘플 추가
            from .models import TOPIC_HEADERS

            backend._write_rows(
                backend.topic_path,
                [
                    TOPIC_HEADERS,
                    ["T001", "신규 회계 자동화 SaaS 출시", "회계 업무에 지친 중소기업 재무담당자", ""],
                    ["T002", "스포츠 산업 채용 모니터링 서비스", "스포츠 업계 이직을 노리는 3년차 마케터", ""],
                ],
            )
            print(f"🌱 샘플 주제 시드 완료 → {backend.topic_path}")


def cmd_check(config: Config, args) -> None:
    """구글 시트 연동 상태를 점검한다(서비스 계정 이메일·시트 접근 확인)."""
    if config.backend != "google":
        print(f"backend={config.backend} (로컬 모드). 구글 점검은 --backend google 로 실행하세요.")
        return

    # 서비스 계정 이메일을 키 파일에서 읽어 안내
    import json

    if not config.google_credentials:
        print("❌ GOOGLE_SERVICE_ACCOUNT_JSON 경로가 설정되지 않았습니다.")
        return
    try:
        sa_email = json.load(open(config.google_credentials, encoding="utf-8")).get(
            "client_email", "(알 수 없음)"
        )
    except Exception as exc:
        print(f"❌ 서비스 계정 키 파일을 읽을 수 없습니다: {exc}")
        return

    print(f"🔑 서비스 계정: {sa_email}")
    print(f"   이 이메일을 대상 스프레드시트에 '편집자'로 공유했는지 확인하세요.")

    try:
        backend = get_backend(config)  # 여기서 인증 + open_by_key 수행
        from .sheets import GoogleSheetBackend

        assert isinstance(backend, GoogleSheetBackend)
        title = backend.sh.title
        tabs = [ws.title for ws in backend.sh.worksheets()]
        print(f"✅ 스프레드시트 접근 성공: '{title}'")
        print(f"   워크시트 탭: {tabs}")
        backend.ensure_headers()
        print(f"✅ '{config.topic_worksheet}' / '{config.draft_worksheet}' 탭 준비 완료")
    except Exception as exc:
        print(f"❌ 시트 접근 실패: {exc}")
        print("   확인: (1) 시트를 서비스 계정 이메일과 공유했는지 "
              "(2) SPREADSHEET_ID가 맞는지 (3) Sheets/Drive API 활성화 여부")


def cmd_generate(config: Config, args) -> None:
    backend = get_backend(config)
    backend.ensure_headers()
    topics = [t for t in backend.read_topics() if not t.is_processed]
    if not topics:
        print("처리할 신규 주제가 없습니다.")
        return

    print(f"📝 {len(topics)}개 주제에 대해 카피 생성 시작 (모델={config.claude_model})")
    for t in topics:
        print(f"  • [{t.id}] {t.topic}")
        angles = generate_angles(config, t)
        backend.append_copies(angles)
        backend.mark_topic_processed(t)
        print(f"    → {len(angles)}개 앵글 시트 기입 완료")

    print("✅ 완료. 담당자가 초안 시트에서 '승인' 표기 후 export/render 를 실행하세요.")


def _load_approved(config: Config) -> list[CopyAngle]:
    backend = get_backend(config)
    approved = backend.read_approved_copies()
    if not approved:
        print("⚠️  '승인'된 카피가 없습니다. 초안 시트의 '승인' 열을 확인하세요.")
    return approved


def cmd_export(config: Config, args) -> None:
    approved = _load_approved(config)
    if not approved:
        return
    out = Path(args.out or (config.output_dir / "figma_import.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "brand": {
            "name": config.brand.name,
            "primary": config.brand.primary,
            "secondary": config.brand.secondary,
            "ink": config.brand.ink,
            "cardWidth": config.brand.card_width,
            "cardHeight": config.brand.card_height,
        },
        "cards": [c.to_dict() for c in approved],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 승인 카피 {len(approved)}개 → 피그마 임포트 JSON 저장: {out}")
    print("   피그마에서 플러그인 실행 → 이 JSON을 붙여넣어 카드 프레임을 생성하세요.")


def cmd_render(config: Config, args) -> None:
    approved = _load_approved(config)
    if not approved:
        return
    from .renderer import render_angle

    out_dir = Path(args.out or config.output_dir)
    print(f"🎨 승인 카피 {len(approved)}개 렌더링 (이미지={'on' if not args.no_image else 'off'})")
    total = 0
    for i, angle in enumerate(approved, start=1):
        paths = render_angle(
            config, angle, out_dir, index=i, make_image=not args.no_image
        )
        total += len(paths)
        print(f"  • [{angle.topic_id}] {angle.angle_name} → {len(paths)}장")
    print(f"✅ 총 {total}장 카드 렌더링 완료 → {out_dir}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cardnews", description="카드뉴스 자동 생성 파이프라인")
    p.add_argument("--backend", choices=["local", "google"], help="시트 백엔드 (기본: 환경변수)")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="시트 헤더 생성 + 로컬 샘플 시드")
    sp.add_argument("--no-seed", dest="seed", action="store_false")
    sp.set_defaults(func=cmd_init, seed=True)

    sp = sub.add_parser("check", help="구글 시트 연동 상태 점검 (서비스 계정·시트 접근)")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("generate", help="주제 → Claude P.D.A. 5앵글 카피 생성")
    sp.set_defaults(func=cmd_generate)

    sp = sub.add_parser("export", help="승인 카피 → 피그마 임포트 JSON")
    sp.add_argument("--out", help="출력 JSON 경로")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("render", help="승인 카피 → 카드 PNG 렌더링")
    sp.add_argument("--out", help="출력 디렉터리")
    sp.add_argument("--no-image", action="store_true", help="OpenAI 이미지 생성 생략")
    sp.set_defaults(func=cmd_render)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = _apply_common(Config(), args)
    args.func(config, args)


if __name__ == "__main__":
    main()
