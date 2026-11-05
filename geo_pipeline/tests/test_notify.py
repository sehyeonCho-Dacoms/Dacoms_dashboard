"""알림 (D-046) — 네트워크 불필요."""

from pipeline import notify


def test_pick_lines_only_fail_and_alert():
    log = "🧭 G3 ...\n   1등 → N-012\n⏸ [G3] 후보 1건 · 조치: 보충\n❌ G3: 후보 없음\n   ⚠️ 세부"
    assert notify.pick_lines(log) == ["⏸ [G3] 후보 1건 · 조치: 보충", "❌ G3: 후보 없음"]


def test_send_skips_without_webhook(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    assert "건너뜀" in notify.send("t", "❌ x")
    assert notify.send("t", "평범한 줄") == "   알림 없음"


def test_send_posts_with_webhook(monkeypatch):
    sent = []
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example/x")
    monkeypatch.setattr(notify._http, "post_raw", lambda url, payload, timeout=0: sent.append((url, payload)) or "ok")
    assert "1건" in notify.send("GEO", "⏸ [G1] 재고 3개 · 조치: 채택", "https://run")
    assert sent[0][1]["text"].startswith("*GEO*") and "[G1]" in sent[0][1]["text"] and "https://run" in sent[0][1]["text"]


def test_alert_format():
    assert notify.alert("G3", "빈칸", "할 일") == "⏸ [G3] 빈칸 · 조치: 할 일 · 담당: 세현"
    assert notify.alert("G4~G6", "멈춤", "세션").endswith("담당: 웅서")
    assert notify.alert("G7·G8", "불일치", "정정", owner="손댄 사람").endswith("담당: 손댄 사람")


def test_fail_line_shown_as_stop_in_slack():
    msg = notify.message("GEO", ["❌ G3: 후보 없음"])
    assert "⛔ G3: 후보 없음" in msg and "❌" not in msg


def test_daily_ok_only_when_clean(monkeypatch):
    sent = []
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example/x")
    monkeypatch.setattr(notify._http, "post_raw", lambda url, payload, timeout=0: sent.append(payload) or "ok")
    assert notify.send("G8", "평범한 줄") == "   알림 없음" and not sent   # 안전망: 문제 없으면 조용히
    assert "✅" in notify.send("G8", "📏 G8: 20편", daily=True, summary=["📏 G8: 20편"])
    assert sent[-1]["text"].startswith("✅ *G8* 문제 없음") and "20편" in sent[-1]["text"]
    notify.send("G8", "⏸ [G8] x · 조치: y", daily=True, summary=["📏"])
    assert "✅" not in sent[-1]["text"] and "⏸ [G8]" in sent[-1]["text"]
