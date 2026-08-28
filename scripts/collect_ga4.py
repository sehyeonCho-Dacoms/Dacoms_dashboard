#!/usr/bin/env python3
"""
드래프트온 대시보드 — GA4 일간 지표 수집기

환경변수:
  GA4_SA_KEY       : 서비스 계정 JSON 키 파일의 "전체 내용" (문자열)
  GA4_PROPERTY_ID  : GA4 속성 ID (숫자 9자리. G-XXXXXXX 아님)

사용법:
  python scripts/collect_ga4.py              # 실제 수집
  python scripts/collect_ga4.py --dry-run    # 키 없이 스키마만 생성 (구조 검증용)
  python scripts/collect_ga4.py --days 28    # 수집 기간 변경 (기본 56일 = 8주)

출력:
  data/ga4_daily.json

주의:
  - 이 저장소는 공개 저장소이므로 pagePath는 쿼리스트링 제거 + ID 정규화 후 저장한다.
  - 시크릿은 어떤 경우에도 stdout/stderr에 출력하지 않는다.
"""

import argparse
import json
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone

DATA_DIR = "data"
OUT_PATH = os.path.join(DATA_DIR, "ga4_daily.json")
DEFAULT_DAYS = 56  # 8주

# 인스타그램 유입으로 간주할 sessionSource 값들
INSTAGRAM_SOURCES = {
    "instagram",
    "instagram.com",
    "l.instagram.com",
    "ig",
    "instagram_stories",
}


# ---------------------------------------------------------------- 경로 정규화
_NUM = re.compile(r"^\d{2,}$")
_HEX = re.compile(r"^[0-9a-fA-F]{16,}$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def normalize_path(path: str) -> str:
    """쿼리스트링·프래그먼트를 제거하고 ID로 보이는 세그먼트를 치환한다.

    /job/128374?utm_source=ig  ->  /job/:id
    /user/a3f9c1b2e8d7f6a5     ->  /user/:hash
    """
    if not path:
        return "/"
    path = path.split("?", 1)[0].split("#", 1)[0]
    out = []
    for seg in path.split("/"):
        if _UUID.match(seg):
            out.append(":uuid")
        elif _NUM.match(seg):
            out.append(":id")
        elif _HEX.match(seg):
            out.append(":hash")
        else:
            out.append(seg)
    return "/".join(out) or "/"


# ---------------------------------------------------------------- GA4 클라이언트
def build_client():
    from google.oauth2 import service_account
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    raw = os.environ.get("GA4_SA_KEY")
    if not raw:
        sys.exit("[FATAL] 환경변수 GA4_SA_KEY 가 없습니다.")
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit("[FATAL] GA4_SA_KEY 가 올바른 JSON 이 아닙니다. "
                 "키 파일 전체 내용을 그대로 넣었는지 확인하세요.")

    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/analytics.readonly"]
    )
    return BetaAnalyticsDataClient(credentials=creds)


def run_report(client, property_id, name, dims, mets, start, end="yesterday",
               limit=100000):
    """단일 리포트 실행. 실패 시 어떤 리포트인지만 남기고 빈 리스트 반환."""
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric,
    )
    try:
        res = client.run_report(RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[DateRange(start_date=start, end_date=end)],
            dimensions=[Dimension(name=d) for d in dims],
            metrics=[Metric(name=m) for m in mets],
            limit=limit,
        ))
    except Exception as exc:  # noqa: BLE001
        # 시크릿이 섞일 수 있으므로 예외 타입과 리포트명만 남긴다
        print(f"[ERROR] report='{name}' failed: {type(exc).__name__}",
              file=sys.stderr)
        print(f"[ERROR] detail: {str(exc)[:300]}", file=sys.stderr)
        return []

    dim_names = [h.name for h in res.dimension_headers]
    met_names = [h.name for h in res.metric_headers]
    rows = []
    for r in res.rows:
        row = {}
        for i, d in enumerate(dim_names):
            row[d] = r.dimension_values[i].value
        for i, m in enumerate(met_names):
            v = r.metric_values[i].value
            try:
                row[m] = round(float(v), 4) if "." in v else int(v)
            except ValueError:
                row[m] = v
        rows.append(row)
    print(f"[OK] report='{name}' rows={len(rows)}", file=sys.stderr)
    return rows


# ---------------------------------------------------------------- 파생 지표
def aggregate_top_pages(rows, top_n=50):
    """정규화된 경로 기준으로 합산 후 상위 N개."""
    bucket = {}
    for r in rows:
        key = normalize_path(r.get("pagePath", ""))
        b = bucket.setdefault(key, {"pagePath": key,
                                    "screenPageViews": 0,
                                    "userEngagementDuration": 0})
        b["screenPageViews"] += int(r.get("screenPageViews") or 0)
        b["userEngagementDuration"] += int(r.get("userEngagementDuration") or 0)
    ranked = sorted(bucket.values(), key=lambda x: -x["screenPageViews"])
    return ranked[:top_n]


def instagram_sessions_by_date(by_source_rows):
    """날짜별 인스타그램 유입 세션 수. 인스타 전환율 계산의 분자."""
    agg = {}
    for r in by_source_rows:
        src = (r.get("sessionSource") or "").lower()
        if src in INSTAGRAM_SOURCES or "instagram" in src:
            d = r.get("date")
            agg[d] = agg.get(d, 0) + int(r.get("sessions") or 0)
    return [{"date": d, "sessions": s} for d, s in sorted(agg.items())]


# ---------------------------------------------------------------- 더미 데이터
def dummy_payload(days):
    random.seed(42)
    today = datetime.now(timezone.utc).date()
    dates = [(today - timedelta(days=i)).strftime("%Y%m%d")
             for i in range(days, 0, -1)]
    channels = ["Organic Search", "Direct", "Organic Social",
                "Referral", "Paid Social", "Unassigned"]
    sources = [("google", "organic"), ("(direct)", "(none)"),
               ("instagram", "referral"), ("l.instagram.com", "referral"),
               ("naver", "organic")]

    daily, by_channel, by_source, by_device, events = [], [], [], [], []
    for d in dates:
        s = random.randint(120, 480)
        daily.append({
            "date": d, "sessions": s,
            "totalUsers": int(s * 0.82), "newUsers": int(s * 0.41),
            "screenPageViews": int(s * 3.2),
            "engagementRate": round(random.uniform(0.45, 0.72), 4),
            "averageSessionDuration": round(random.uniform(60, 220), 2),
        })
        for c in channels:
            by_channel.append({"date": d, "sessionDefaultChannelGroup": c,
                               "sessions": random.randint(5, 160),
                               "totalUsers": random.randint(4, 140)})
        for src, med in sources:
            by_source.append({"date": d, "sessionSource": src,
                              "sessionMedium": med,
                              "sessions": random.randint(2, 90)})
        for dev in ["mobile", "desktop", "tablet"]:
            by_device.append({"date": d, "deviceCategory": dev,
                              "sessions": random.randint(3, 300)})
        for ev in ["page_view", "session_start", "sign_up",
                   "job_view", "apply_complete"]:
            events.append({"date": d, "eventName": ev,
                           "eventCount": random.randint(1, 900)})

    top_pages = [{"pagePath": p, "screenPageViews": random.randint(50, 900),
                  "userEngagementDuration": random.randint(500, 9000)}
                 for p in ["/", "/jobs", "/job/:id", "/company/:id",
                           "/signup", "/mypage", "/talent-pool"]]

    return {
        "daily": daily, "by_channel": by_channel, "by_source": by_source,
        "by_device": by_device, "events": events, "top_pages": top_pages,
        "instagram_referral": instagram_sessions_by_date(by_source),
    }


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="API 호출 없이 더미 데이터로 JSON 스키마만 생성")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    args = ap.parse_args()

    start = f"{args.days}daysAgo"

    if args.dry_run:
        print("[DRY-RUN] GA4 API를 호출하지 않고 더미 데이터를 생성합니다.",
              file=sys.stderr)
        body = dummy_payload(args.days)
        prop = "DRY_RUN"
    else:
        prop = os.environ.get("GA4_PROPERTY_ID")
        if not prop:
            sys.exit("[FATAL] 환경변수 GA4_PROPERTY_ID 가 없습니다.")
        if not prop.isdigit():
            sys.exit("[FATAL] GA4_PROPERTY_ID 는 숫자여야 합니다. "
                     "측정 ID(G-XXXXXXX)가 아니라 '속성 ID'를 넣으세요.")

        client = build_client()
        R = lambda n, d, m: run_report(client, prop, n, d, m, start)  # noqa: E731

        by_source = R("by_source", ["date", "sessionSource", "sessionMedium"],
                      ["sessions"])
        raw_pages = R("top_pages", ["pagePath"],
                      ["screenPageViews", "userEngagementDuration"])

        body = {
            "daily": R("daily", ["date"],
                       ["sessions", "totalUsers", "newUsers",
                        "screenPageViews", "engagementRate",
                        "averageSessionDuration"]),
            "by_channel": R("by_channel",
                            ["date", "sessionDefaultChannelGroup"],
                            ["sessions", "totalUsers"]),
            "by_source": by_source,
            "by_device": R("by_device", ["date", "deviceCategory"],
                           ["sessions"]),
            "events": R("events", ["date", "eventName"], ["eventCount"]),
            "top_pages": aggregate_top_pages(raw_pages),
            "instagram_referral": instagram_sessions_by_date(by_source),
        }

        if not body["daily"]:
            sys.exit("[FATAL] 'daily' 리포트가 비어 있습니다. 속성 ID 또는 "
                     "서비스 계정 권한(뷰어)을 확인하세요.")

    # GA4는 행 순서를 보장하지 않으므로 날짜 기준으로 정렬해 둔다.
    for k, v in body.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "date" in v[0]:
            body[k] = sorted(v, key=lambda r: r.get("date", ""))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "Asia/Seoul",
        "property_id": prop if prop == "DRY_RUN" else "***",
        "range_days": args.days,
        **body,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[DONE] {OUT_PATH} 생성 완료 "
          f"(daily {len(payload['daily'])}일치)", file=sys.stderr)


if __name__ == "__main__":
    main()
