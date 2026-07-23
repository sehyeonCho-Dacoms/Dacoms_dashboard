"""파이프라인 보조 명령어 — 피그마 플러그인 실행 전 로컬 서버를 단독으로 띄울 때 사용.

    python3 pipeline.py serve

orchestrator.py가 이미 마지막 단계에서 figma_agent.serve()를 호출하지만,
이미 승인된 세트를 다시 피그마로 보내고 싶을 때 이 명령으로 서버만
단독 실행할 수 있다.
"""

from __future__ import annotations

import argparse

import figma_agent


def main():
    parser = argparse.ArgumentParser(description="파이프라인 보조 명령")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="피그마 플러그인용 로컬 서버(포트 8765) 시작")
    args = parser.parse_args()

    if args.command == "serve":
        figma_agent.serve()


if __name__ == "__main__":
    main()
