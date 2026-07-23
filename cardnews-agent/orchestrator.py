"""오케스트레이터 — 3개 에이전트를 하나의 명령어로 묶어 실행한다.

    python3 orchestrator.py all --persona "..." --desire "..." \
        --awareness problem-aware --auto

단계: 썸네일 생성 → (승인 대기) → 본문 생성 → (승인 대기) → 피그마 서버(플러그인으로 연결)
--auto 를 주면 각 단계의 승인을 자동으로 통과시키고 사람의 개입 없이 끝까지 실행한다.
"""

from __future__ import annotations

import argparse

import body_agent
import figma_agent
import image_agent
import thumbnail_agent


def run_all(persona: str, desire: str, awareness: str, auto: bool = False) -> None:
    thumbnail_agent.generate_thumbnails(persona, desire, awareness, auto=auto)

    if not auto:
        print(
            "\n⏸  시트에서 마음에 드는 앵글의 K열(썸네일 상태)을 "
            "'썸네일 승인'으로 바꾼 뒤 Enter를 누르세요..."
        )
        input()

    body_agent.process_approved_thumbnails(auto=auto)

    if not auto:
        print(
            "\n⏸  시트에서 U열(본문 상태)을 '본문 승인'으로 바꾼 뒤 Enter를 누르세요..."
        )
        input()

    image_agent.process_approved_bodies()

    print()
    figma_agent.serve()


def main():
    parser = argparse.ArgumentParser(description="카드뉴스 에이전트 오케스트레이터")
    sub = parser.add_subparsers(dest="command", required=True)

    p_all = sub.add_parser("all", help="전체 파이프라인 실행")
    p_all.add_argument("--persona", required=True, help="타겟 페르소나")
    p_all.add_argument("--desire", required=True, help="페르소나의 욕구/고민")
    p_all.add_argument(
        "--awareness",
        default="problem-aware",
        choices=["unaware", "problem-aware", "solution-aware", "product-aware"],
    )
    p_all.add_argument("--auto", action="store_true", help="승인 단계 없이 완전 자동 실행")

    args = parser.parse_args()
    if args.command == "all":
        try:
            run_all(args.persona, args.desire, args.awareness, auto=args.auto)
        except Exception as exc:
            print(f"❌ 파이프라인 실패: {exc}")
            raise SystemExit(1)


if __name__ == "__main__":
    main()
