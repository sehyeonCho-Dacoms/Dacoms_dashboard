"""피그마 에이전트 — 로컬 HTTP 서버(포트 8765)로 카드 데이터를 플러그인에 전달.

image_agent.py가 렌더링한 카드 배경 PNG + 시트의 카피 텍스트를 묶어
import.json 형태로 서빙한다. 피그마 플러그인(code.js)이 이 서버에서
데이터를 fetch해 마스터 프레임을 복제·채운다.

    Python 서버 (포트 8765)  ←  데이터 요청  →  피그마 플러그인 (code.js)

플러그인이 카드 생성을 마치면 POST /complete 로 완료를 알려오고,
서버는 해당 세트의 '본문 상태' 열을 'Figma 생성 완료'로 갱신한다.
"""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sheet_client import SheetClient, STATUS_BODY_APPROVED, STATUS_FIGMA_DONE, STATUS_IMAGE_IN_PROGRESS

PORT = 8765
OUTPUT_DIR = Path(__file__).parent / "output"

# figma-plugin/code.js가 프레임을 찾을 때 쓰는 이름 매핑 규칙: "마스터_" + frame_name
FOLLOW_TEXT_DEFAULT = "팔로우하기"


def _load_config_brand_label() -> str:
    import yaml

    cfg_path = Path(__file__).parent / "config.yaml"
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        return cfg.get("brand_label", "브랜드")
    return "브랜드"


def _encode_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def build_import_payload() -> dict:
    """이미지 렌더링이 끝났지만 아직 Figma에 반영되지 않은 세트들을 모아 payload 구성."""
    sheet = SheetClient()
    sheet.ensure_headers()

    rows = [
        r
        for r in sheet.read_all()
        if r.get("본문 상태") == STATUS_BODY_APPROVED
        and r.get("PNG 폴더", "").strip()
        and r.get("PNG 폴더") != STATUS_IMAGE_IN_PROGRESS
        and r.get("PNG 폴더") != STATUS_FIGMA_DONE
    ]

    brand_label = _load_config_brand_label()
    card_sets = []
    for row in rows:
        folder = Path(row["PNG 폴더"])
        if not folder.exists():
            continue

        headline_lines = row.get("Card01 헤드라인", "").split("\n")
        headline_text = "\n".join(headline_lines)

        images = [
            {
                "filename": "01_thumbnail.png",
                "frame_name": "썸네일",
                "data": _encode_file(folder / "01_thumbnail.png"),
                "texts": [headline_text, row.get("Card01 칩2", ""), row.get("Card01 칩1", "")],
            },
            {
                "filename": "02_body1.png",
                "frame_name": "본문_1",
                "data": _encode_file(folder / "02_body1.png"),
                "texts": [row.get("Card02 섹션타이틀", ""), row.get("Card02 인풋텍스트", "")],
            },
            {
                "filename": "03_body2.png",
                "frame_name": "본문_2",
                "data": _encode_file(folder / "03_body2.png"),
                "texts": [row.get("Card03 섹션타이틀", ""), row.get("Card03 인풋텍스트", "")],
            },
            {
                "filename": "04_body3.png",
                "frame_name": "본문_1",
                "data": _encode_file(folder / "04_body3.png"),
                "texts": [row.get("Card04 섹션타이틀", ""), row.get("Card04 인풋텍스트", "")],
            },
            {
                "filename": "05_cta.png",
                "frame_name": "CTA",
                "data": _encode_file(folder / "05_cta.png"),
                "texts": [row.get("Card05 CTA 유도문구", ""), f"{brand_label} {FOLLOW_TEXT_DEFAULT}"],
                "keep_background": True,
            },
        ]
        card_sets.append({"folder_name": row.get("폴더명", folder.name), "images": images})

    return {"card_sets": card_sets}


def _make_handler():
    payload_cache = {"data": None}

    class Handler(BaseHTTPRequestHandler):
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            if self.path == "/import.json":
                if payload_cache["data"] is None:
                    payload_cache["data"] = build_import_payload()
                body = json.dumps(payload_cache["data"], ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._cors()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                n = len(payload_cache["data"].get("card_sets", []))
                print(f"  📦 /import.json 서빙 — {n}개 세트")
            else:
                self.send_response(404)
                self._cors()
                self.end_headers()

        def do_POST(self):
            if self.path == "/complete":
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {}
                folder_name = data.get("folder_name")
                if folder_name:
                    sheet = SheetClient()
                    for row in sheet.read_all():
                        if row.get("폴더명") == folder_name:
                            sheet.update_row(row["_row"], {"PNG 폴더": STATUS_FIGMA_DONE})
                    print(f"  ✅ Figma 생성 완료 처리: {folder_name}")
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
            else:
                self.send_response(404)
                self._cors()
                self.end_headers()

        def log_message(self, fmt, *args):
            pass  # 기본 접근 로그는 조용히 무시(위의 print로 대체)

    return Handler


def serve(block_for_enter: bool = True) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("localhost", PORT), _make_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"🎨 Figma 플러그인 서버 시작 — http://localhost:{PORT}/import.json")
    print("   Figma Desktop에서 플러그인을 실행하세요.")

    if block_for_enter:
        print("   서버를 종료하려면 Enter를 누르세요...")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        server.shutdown()
        print("서버 종료됨.")
    return server


if __name__ == "__main__":
    serve()
