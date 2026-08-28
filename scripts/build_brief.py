#!/usr/bin/env python3
"""
드래프트온 — 데일리 브리핑용 요약 생성기

data/ga4_daily.json + data/ga4_weekly.json 을 읽어, 매일 9시 Slack 브리핑이
그대로 쓸 수 있는 작은 요약(data/ga4_brief.json, 약 3KB)을 만든다.

왜 필요한가:
  ga4_daily.json 은 180KB 이상이라 브리핑 세션이 통째로 읽으면 요약되면서
  숫자가 부정확해진다. 필요한 값만 미리 계산해 작은 파일로 떨어뜨린다.

API를 호출하지 않으므로 collect_ga4.py → build_weekly.py 다음에 실행하면 된다.

사용법:
  python scripts/build_brief.py
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

DAILY = os.path.join("data", "ga4_daily.json")
WEEKLY = os.path.join("data", "ga4_weekly.json")
OUT = os.path.join("data", "ga4_brief.json")

# 8/27 GTM 재구축으로 새로 만든 계측 이벤트 (끊기면 즉시 알아야 하는 것들)
WATCH_EVENTS = [
    ("recruit_view", "공고 상세"),
    ("recruit_list_view", "공고 목록"),
    ("apply_start", "지원 시작"),
    ("apply_resume_selected", "이력서 선택"),
    ("apply_click_final", "최종 지원"),
    ("sign_up_start", "가입 시작"),
    ("resume_new_start", "이력서 작성"),
    ("resume_edit_start", "이력서 수정"),
    ("resume_save_click", "이력서 저장"),
]

# 8/3 계측 유실 이전의 '정상' 주간 — 진짜 성장폭을 재는 기준선
BASELINE_WEEKS = [("20260722", "20260728"), ("20260729", "20260804")]


def main():
    for p in (DAILY, WEEKLY):
        if not os.path.exists(p):
            sys.exit(f"[FATAL] {p} 가 없습니다. collect_ga4.py / build_weekly.py 를 먼저 실행하세요.")

    d = json.load(open(DAILY, encoding="utf-8"))
    w = json.load(open(WEEKLY, encoding="utf-8"))

    daily = sorted(d.get("daily", []), key=lambda r: r.get("date", ""))
    if not daily:
        sys.exit("[FATAL] daily 데이터가 비어 있습니다.")

    dates = [r["date"] for r in daily]
    last = daily[-1]

    # ---- 어제(마지막 확정일)
    yesterday = {
        "date": last["date"],
        "sessions": int(last.get("sessions") or 0),
        "totalUsers": int(last.get("totalUsers") or 0),
        "newUsers": int(last.get("newUsers") or 0),
        "engagementRate": round(float(last.get("engagementRate") or 0), 4),
        "averageSessionDuration": round(float(last.get("averageSessionDuration") or 0), 1),
    }
    prev = daily[-2] if len(daily) > 1 else None
    if prev:
        ps = int(prev.get("sessions") or 0)
        yesterday["sessions_prev_day"] = ps
        yesterday["sessions_dod_pct"] = (
            round((yesterday["sessions"] - ps) / ps * 100, 1) if ps else None
        )

    # ---- 계측 유실 이전 기준선과의 비교
    trend = w.get("weekly_trend", [])
    base_vals = [
        t["sessions"] for t in trend
        if (t.get("week_start"), t.get("week_end")) in BASELINE_WEEKS
    ]
    cur_week = (w.get("summary", {}).get("sessions", {}) or {}).get("current")
    baseline = None
    if base_vals and cur_week:
        avg = sum(base_vals) / len(base_vals)
        baseline = {
            "note": "8/3 계측 유실 이전 정상 주간 평균 대비 — 이쪽이 진짜 성장폭",
            "baseline_avg_sessions": round(avg),
            "current_week_sessions": cur_week,
            "change_pct": round((cur_week - avg) / avg * 100, 1),
        }

    # ---- 계측 상태 (최근 3일)
    ev = defaultdict(dict)
    for r in d.get("events", []):
        ev[r["eventName"]][r["date"]] = int(r.get("eventCount") or 0)

    recent3 = dates[-3:]
    events, broken = [], []
    for name, label in WATCH_EVENTS:
        counts = [ev.get(name, {}).get(dt, 0) for dt in recent3]
        alive = counts[-1] > 0
        events.append({"event": name, "label": label,
                       "dates": recent3, "counts": counts, "alive": alive})
        if not alive:
            broken.append(label)

    # ---- 경고
    alerts = []
    gen = d.get("generated_at", "")
    if gen[:10] != datetime.now(timezone.utc).strftime("%Y-%m-%d"):
        alerts.append(f"데이터 미갱신 — 마지막 수집 {gen[:16]} (UTC). Actions 실행 확인 필요")
    if broken:
        alerts.append("계측 끊김 의심 — " + ", ".join(broken) + f" ({recent3[-1]} 0건)")
    dod = yesterday.get("sessions_dod_pct")
    if dod is not None and abs(dod) >= 30:
        alerts.append(f"세션 급변 — 전일 대비 {dod:+.1f}%")
    er = yesterday["engagementRate"]
    if er and (er < 0.35 or er > 0.9):
        alerts.append(f"참여율 이상치 {er*100:.1f}% — GA4 미확정 데이터일 수 있음")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_generated_at": gen,
        "yesterday": yesterday,
        "week": w.get("summary", {}),
        "window": w.get("window", {}),
        "baseline_comparison": baseline,
        "channels": w.get("by_channel", [])[:6],
        "instagram_referral": w.get("instagram_referral", {}),
        "weekly_trend": trend[-8:],
        "measurement": {"recent_dates": recent3, "events": events, "broken": broken},
        "alerts": alerts,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[DONE] {OUT} 생성 완료 (경고 {len(alerts)}건, 계측 끊김 {len(broken)}건)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
