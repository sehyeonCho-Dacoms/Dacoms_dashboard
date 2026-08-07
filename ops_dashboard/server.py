"""다컴스 운영 통합 대시보드 — 로컬 전용 서버.

표준 라이브러리만 사용한다(이 저장소의 다른 파이프라인과 동일 원칙).
채용 리드(data/dashboard.json)·카드뉴스 성과(data/card_news_metrics.csv)·
7개 서브에이전트 실행 현황(outputs/*/latest.json)은 읽기 전용으로 보여주고,
타겟 기업 CRM(data/target_companies.csv)만 이 대시보드에서 직접 편집할 수
있다 — 나머지는 각 파이프라인이 재실행할 때마다 덮어써지는 산출물이라
여기서 고쳐봐야 다음 실행에 사라지기 때문이다.

반드시 로컬(127.0.0.1)에서만 열어야 한다 — 인증이 없고 실제 파일을
직접 쓰기 때문에, 외부에 노출하면 누구나 타겟 기업 CRM을 고칠 수 있다.
"""

from __future__ import annotations

import argparse
import csv
import http.server
import json
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUTS_DIR = REPO_ROOT / "outputs"
STATIC_DIR = Path(__file__).resolve().parent / "static"

JOBS_JSON = DATA_DIR / "dashboard.json"
TARGETS_CSV = DATA_DIR / "target_companies.csv"
METRICS_CSV = DATA_DIR / "card_news_metrics.csv"

TARGET_FIELDS = [
    "id", "company", "sector", "tier", "lead_score", "rationale",
    "source", "contact_status", "next_action", "notes",
]
EDITABLE_TARGET_FIELDS = {f for f in TARGET_FIELDS if f != "id"}

AGENT_TEAMS = [
    "job-posting-collector", "metrics-analyzer", "daily-briefing",
    "card-news-planner", "card-news-designer", "content-risk-reviewer",
    "cold-email-team",
]


# --------------------------------------------------------------------------- #
# 데이터 읽기/쓰기
# --------------------------------------------------------------------------- #
def read_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"__error__": f"{path.name} 파싱 실패: {e}"}


def read_targets() -> list[dict]:
    if not TARGETS_CSV.exists():
        return []
    with TARGETS_CSV.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_targets(rows: list[dict]) -> None:
    TARGETS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with TARGETS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TARGET_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in TARGET_FIELDS})


def read_metrics():
    if not METRICS_CSV.exists():
        return None
    with METRICS_CSV.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def read_agent_outputs() -> dict:
    return {team: read_json(OUTPUTS_DIR / team / "latest.json") for team in AGENT_TEAMS}


def next_target_id(rows: list[dict]) -> str:
    nums = []
    for r in rows:
        rid = r.get("id") or ""
        if rid.startswith("co-"):
            try:
                nums.append(int(rid[3:]))
            except ValueError:
                pass
    return f"co-{(max(nums) + 1) if nums else 1:03d}"


def build_state() -> dict:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "jobs": read_json(JOBS_JSON),
        "targets": read_targets(),
        "metrics": read_metrics(),
        "agents": read_agent_outputs(),
    }


# --------------------------------------------------------------------------- #
# HTTP 핸들러
# --------------------------------------------------------------------------- #
class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "DacomsOpsDashboard/0.1"

    def log_message(self, fmt, *args):  # 콘솔 로그를 조용히
        pass

    def _send_json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, path: Path) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path in ("/", "/index.html"):
            return self._send_html(STATIC_DIR / "index.html")
        if path == "/api/state":
            return self._send_json(build_state())
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/targets":
            body = self._read_json_body()
            company = str(body.get("company", "")).strip()
            if not company:
                return self._send_json({"error": "company는 필수입니다"}, status=400)
            rows = read_targets()
            row = {k: str(body.get(k, "")).strip() for k in EDITABLE_TARGET_FIELDS}
            row["id"] = next_target_id(rows)
            row.setdefault("contact_status", "검토 필요")
            rows.append(row)
            write_targets(rows)
            return self._send_json({"ok": True, "row": row})
        self._send_json({"error": "not found"}, status=404)

    def do_PUT(self) -> None:
        parts = urllib.parse.urlsplit(self.path).path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "targets":
            target_id = urllib.parse.unquote(parts[2])
            body = self._read_json_body()
            rows = read_targets()
            match = next((r for r in rows if r.get("id") == target_id), None)
            if match is None:
                return self._send_json({"error": "존재하지 않는 id"}, status=404)
            for k, v in body.items():
                if k in EDITABLE_TARGET_FIELDS:
                    match[k] = str(v)
            write_targets(rows)
            return self._send_json({"ok": True, "row": match})
        self._send_json({"error": "not found"}, status=404)

    def do_DELETE(self) -> None:
        parts = urllib.parse.urlsplit(self.path).path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "targets":
            target_id = urllib.parse.unquote(parts[2])
            rows = read_targets()
            kept = [r for r in rows if r.get("id") != target_id]
            if len(kept) == len(rows):
                return self._send_json({"error": "존재하지 않는 id"}, status=404)
            write_targets(kept)
            return self._send_json({"ok": True})
        self._send_json({"error": "not found"}, status=404)


def main() -> None:
    parser = argparse.ArgumentParser(description="다컴스 운영 통합 대시보드 (로컬 전용)")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-browser", action="store_true", help="자동으로 브라우저를 열지 않음")
    args = parser.parse_args()

    # 127.0.0.1로만 바인딩 — 인증 없이 실제 파일을 쓰는 서버이므로 네트워크에 노출 금지
    with http.server.HTTPServer(("127.0.0.1", args.port), Handler) as httpd:
        url = f"http://127.0.0.1:{args.port}"
        print(f"✅ 다컴스 운영 대시보드 실행 중 → {url}")
        print("   (로컬 전용 — 이 주소를 외부에 공유하지 마세요) Ctrl+C로 종료")
        if not args.no_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n종료합니다.")


if __name__ == "__main__":
    main()
