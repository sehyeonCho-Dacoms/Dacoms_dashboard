"""구글 시트 동기화 — 로컬 설치 없이 URL 하나로 관리하기 위한 대안.

`ops_dashboard/server.py`(로컬 서버)를 실행할 수 없는 환경(이 프로젝트를
컴퓨터에 내려받지 않고 전부 채팅으로만 다루는 경우)을 위한 것이다. 구글
시트를 "다 펼쳐서 보고 직접 편집하는" 화면으로 쓰고, 이 스크립트가 그 시트와
저장소의 실제 파일 사이를 동기화한다.

- `push`: 저장소의 최신 데이터(타겟 기업/채용 리드/카드뉴스 성과) → 시트에
  덮어쓰기. 채용 리드·카드뉴스 성과 탭은 항상 이 방향(읽기 전용 뷰).
- `pull`: 시트의 "타겟기업" 탭(사람이 시트에서 직접 편집한 내용) →
  `data/target_companies.csv`. cold-email-team 서브에이전트가 최신 상태를
  읽으려면 이 명령을 먼저 실행해야 한다.

주의: 시트가 "최신"이라는 보장은 마지막으로 push/pull을 실행한 시점까지다 —
실시간 동기화가 아니다. 채용 리드/카드뉴스 성과 탭은 push할 때마다 통째로
덮어쓰므로 시트에서 그 두 탭을 직접 고쳐도 다음 push 때 사라진다(의도된
동작 — 그 데이터의 원본은 파이프라인 산출물이다).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

TARGETS_CSV = DATA_DIR / "target_companies.csv"
JOBS_JSON = DATA_DIR / "dashboard.json"
METRICS_CSV = DATA_DIR / "card_news_metrics.csv"

TARGET_FIELDS = [
    "id", "company", "sector", "tier", "lead_score", "rationale",
    "source", "contact_status", "next_action", "notes",
]
JOBS_TAB = "채용리드"
TARGETS_TAB = "타겟기업"
METRICS_TAB = "카드뉴스성과"

JOBS_HEADER = ["기업", "섹터", "티어", "점수", "오픈", "증감", "시니어", "예상수수료(만원)", "시그널"]
METRICS_HEADER = [
    "post_id", "date", "topic", "sport_category", "format",
    "impressions", "reach", "saves", "shares", "clicks",
    "profile_visits", "apply_clicks",
]


def _config():
    key_path = Path(
        os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "card_news_pipeline/service_account.json")
    )
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        raise SystemExit(
            "SPREADSHEET_ID가 필요합니다. 예)\n"
            "  SPREADSHEET_ID=xxxxx python3 ops_dashboard/sync_sheet.py push"
        )
    if not key_path.exists():
        raise SystemExit(f"서비스 계정 키를 찾을 수 없습니다: {key_path}")
    return key_path, spreadsheet_id


def _open_sheet():
    import gspread
    from google.oauth2.service_account import Credentials

    key_path, spreadsheet_id = _config()
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(str(key_path), scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(spreadsheet_id)


def _get_or_create_tab(sh, title: str, cols: int):
    import gspread

    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=1000, cols=max(10, cols))


# --------------------------------------------------------------------------- #
# push: 저장소 → 시트
# --------------------------------------------------------------------------- #
def push_targets(sh) -> int:
    if not TARGETS_CSV.exists():
        print(f"  ⚠️  {TARGETS_CSV} 없음 — 타겟기업 탭 건너뜀")
        return 0
    with TARGETS_CSV.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    ws = _get_or_create_tab(sh, TARGETS_TAB, len(TARGET_FIELDS))
    ws.clear()
    values = [TARGET_FIELDS] + [[r.get(k, "") for k in TARGET_FIELDS] for r in rows]
    ws.update(values, "A1")
    return len(rows)


def push_jobs(sh) -> int:
    data = json.loads(JOBS_JSON.read_text(encoding="utf-8")) if JOBS_JSON.exists() else None
    ws = _get_or_create_tab(sh, JOBS_TAB, len(JOBS_HEADER))
    ws.clear()
    if not data:
        ws.update([["아직 job_pipeline을 실행하지 않았습니다."]], "A1")
        return 0
    leads = data.get("leads", [])
    rows = [[
        l.get("company", ""), l.get("sector", ""), l.get("tier", ""), l.get("score", ""),
        l.get("open", ""), l.get("growth", ""), l.get("senior", ""), l.get("fee", ""),
        l.get("signal", ""),
    ] for l in leads]
    ws.update([JOBS_HEADER] + rows, "A1")
    return len(rows)


def push_metrics(sh) -> int:
    ws = _get_or_create_tab(sh, METRICS_TAB, len(METRICS_HEADER))
    ws.clear()
    if not METRICS_CSV.exists():
        ws.update([["아직 metrics_pipeline을 실행하지 않았습니다."]], "A1")
        return 0
    with METRICS_CSV.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    values = [METRICS_HEADER] + [[r.get(k, "") for k in METRICS_HEADER] for r in rows]
    ws.update(values, "A1")
    return len(rows)


def cmd_push(args) -> None:
    sh = _open_sheet()
    n1 = push_targets(sh)
    print(f"  • {TARGETS_TAB}: {n1}행 반영")
    n2 = push_jobs(sh)
    print(f"  • {JOBS_TAB}: {n2}행 반영")
    n3 = push_metrics(sh)
    print(f"  • {METRICS_TAB}: {n3}행 반영")
    print(f"✅ push 완료 → {sh.url}")


# --------------------------------------------------------------------------- #
# pull: 시트 → 저장소 (타겟기업만 — 사람이 직접 편집하는 유일한 탭)
# --------------------------------------------------------------------------- #
def cmd_pull(args) -> None:
    sh = _open_sheet()
    ws = _get_or_create_tab(sh, TARGETS_TAB, len(TARGET_FIELDS))
    values = ws.get_all_values()
    if not values:
        print("⚠️  시트가 비어 있습니다. 먼저 push로 초기 데이터를 넣으세요.")
        return
    header, rows = values[0], values[1:]
    idx = {name: i for i, name in enumerate(header)}
    missing = [f for f in TARGET_FIELDS if f not in idx]
    if missing:
        raise SystemExit(f"시트 헤더에 누락된 컬럼: {missing} (헤더를 지우지 마세요)")

    TARGETS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with TARGETS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TARGET_FIELDS)
        w.writeheader()
        for row in rows:
            if not any(row):
                continue
            w.writerow({k: (row[idx[k]] if idx[k] < len(row) else "") for k in TARGET_FIELDS})
    kept = sum(1 for r in rows if any(r))
    print(f"✅ pull 완료: 시트 {kept}행 → {TARGETS_CSV}")


def main() -> None:
    parser = argparse.ArgumentParser(description="구글 시트 ↔ 저장소 동기화")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("push", help="저장소 최신 데이터 → 시트 3개 탭에 반영").set_defaults(func=cmd_push)
    sub.add_parser("pull", help="시트의 타겟기업 탭 → data/target_companies.csv").set_defaults(func=cmd_pull)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
