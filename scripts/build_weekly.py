#!/usr/bin/env python3
"""
드래프트온 대시보드 — 주간 비교 지표 생성기

data/ga4_daily.json 을 읽어 아래를 계산해 data/ga4_weekly.json 으로 저장한다.
  - 최근 7일 vs 직전 7일 총계 및 증감률
  - 채널별 7일 총계 비교
  - 주 단위 8주 추이
  - 인스타그램 유입 세션 주간 추이

API를 호출하지 않으므로 collect_ga4.py 다음에 바로 실행하면 된다.

사용법:
  python scripts/build_weekly.py
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

IN_PATH = os.path.join("data", "ga4_daily.json")
OUT_PATH = os.path.join("data", "ga4_weekly.json")

SUM_METRICS = ["sessions", "totalUsers", "newUsers", "screenPageViews"]
AVG_METRICS = ["engagementRate", "averageSessionDuration"]


def pct(cur, prev):
    """증감률(%). 직전 값이 0이면 None (분모 0 → '신규'로 표기하게)."""
    if not prev:
        return None
    return round((cur - prev) / prev * 100, 1)


def sum_window(rows, dates, keys):
    out = {k: 0 for k in keys}
    for r in rows:
        if r.get("date") in dates:
            for k in keys:
                out[k] += float(r.get(k) or 0)
    return {k: (int(v) if k in SUM_METRICS else round(v, 4))
            for k, v in out.items()}


def avg_window(rows, dates, keys):
    acc = {k: [] for k in keys}
    for r in rows:
        if r.get("date") in dates:
            for k in keys:
                v = r.get(k)
                if v is not None:
                    acc[k].append(float(v))
    return {k: (round(sum(v) / len(v), 4) if v else 0) for k, v in acc.items()}


def main():
    if not os.path.exists(IN_PATH):
        sys.exit(f"[FATAL] {IN_PATH} 가 없습니다. collect_ga4.py 를 먼저 실행하세요.")

    with open(IN_PATH, encoding="utf-8") as f:
        src = json.load(f)

    daily = sorted(src.get("daily", []), key=lambda r: r.get("date", ""))
    if len(daily) < 14:
        print(f"[WARN] 일간 데이터가 {len(daily)}일치뿐이라 주간 비교가 "
              f"부정확할 수 있습니다.", file=sys.stderr)

    all_dates = [r["date"] for r in daily]
    last7 = set(all_dates[-7:])
    prev7 = set(all_dates[-14:-7])

    cur_sum = sum_window(daily, last7, SUM_METRICS)
    prv_sum = sum_window(daily, prev7, SUM_METRICS)
    cur_avg = avg_window(daily, last7, AVG_METRICS)
    prv_avg = avg_window(daily, prev7, AVG_METRICS)

    summary = {}
    for k in SUM_METRICS:
        summary[k] = {"current": cur_sum[k], "previous": prv_sum[k],
                      "change_pct": pct(cur_sum[k], prv_sum[k])}
    for k in AVG_METRICS:
        summary[k] = {"current": cur_avg[k], "previous": prv_avg[k],
                      "change_pct": pct(cur_avg[k], prv_avg[k])}

    # ---- 채널별 7일 비교
    ch_cur, ch_prv = defaultdict(int), defaultdict(int)
    for r in src.get("by_channel", []):
        ch = r.get("sessionDefaultChannelGroup", "(unknown)")
        s = int(r.get("sessions") or 0)
        if r.get("date") in last7:
            ch_cur[ch] += s
        elif r.get("date") in prev7:
            ch_prv[ch] += s

    by_channel = sorted(
        [{"channel": c, "current": ch_cur.get(c, 0),
          "previous": ch_prv.get(c, 0),
          "change_pct": pct(ch_cur.get(c, 0), ch_prv.get(c, 0))}
         for c in set(ch_cur) | set(ch_prv)],
        key=lambda x: -x["current"],
    )

    total_cur = sum(ch_cur.values()) or 1
    for row in by_channel:
        row["share_pct"] = round(row["current"] / total_cur * 100, 1)

    # ---- 8주 추이 (최신 주가 마지막)
    weeks = []
    idx = len(all_dates)
    while idx - 7 >= 0 and len(weeks) < 8:
        window = set(all_dates[idx - 7:idx])
        agg = sum_window(daily, window, SUM_METRICS)
        weeks.append({
            "week_start": min(window), "week_end": max(window), **agg,
        })
        idx -= 7
    weeks.reverse()

    # ---- 인스타 유입 주간 추이
    ig_rows = src.get("instagram_referral", [])
    ig_cur = sum(int(r["sessions"]) for r in ig_rows if r["date"] in last7)
    ig_prv = sum(int(r["sessions"]) for r in ig_rows if r["date"] in prev7)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_generated_at": src.get("generated_at"),
        "window": {
            "current": {"start": min(last7), "end": max(last7)},
            "previous": {"start": min(prev7), "end": max(prev7)} if prev7 else None,
        },
        "summary": summary,
        "by_channel": by_channel,
        "weekly_trend": weeks,
        "instagram_referral": {
            "current": ig_cur, "previous": ig_prv,
            "change_pct": pct(ig_cur, ig_prv),
            "share_of_sessions_pct": round(ig_cur / total_cur * 100, 1),
        },
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[DONE] {OUT_PATH} 생성 완료 (주간 {len(weeks)}주치)", file=sys.stderr)


if __name__ == "__main__":
    main()
