from datetime import date

from pipeline import g8

TODAY = date(2026, 11, 3)


def _post(**kw):
    base = dict(page_id="p1", no="N-001", channel="네이버 블로그", title="제목", state="게시완료", index="",
                url="https://blog.naver.com/doctoronhr/224449578868", published=date(2026, 10, 22), log="")
    return g8.Post(**{**base, **kw})


def test_due_backfills_latest_missing_checkpoint_only():
    assert g8.due(_post(published=date(2026, 11, 1)), TODAY) is None           # D+2
    assert g8.due(_post(published=date(2026, 10, 31)), TODAY) == 3             # D+3
    assert g8.due(_post(), TODAY) == 7                                          # D+12, 아무것도 안 잼 → D+7
    assert g8.due(_post(log="11/02 G8 D+7 자동: ..."), TODAY) is None
    assert g8.due(_post(log="11/02 G8 D+7(실측 D+11) 자동: ..."), TODAY) is None
    # 웅서 수동 기록 'D+11'은 정식 시점이 아니라 D+7을 다시 잰다
    assert g8.due(_post(log="11/02 G8 D+11(웅서 Claude 수동): 노출 확인"), TODAY) == 7
    assert g8.due(_post(published=date(2026, 10, 1), log="10/08 G8 D+7 자동"), TODAY) == 30


def test_naver_found_matches_log_no():
    url = "https://blog.naver.com/doctoronhr/224449578868"
    assert g8.naver_found([{"link": "https://blog.naver.com/doctoronhr/224449578868"}], url)
    assert g8.naver_found([{"link": "https://m.blog.naver.com/PostView.naver?blogId=doctoronhr&logNo=224449578868"}], url)
    assert not g8.naver_found([{"link": "https://blog.naver.com/other/111111111111"}], url)
    assert not g8.naver_found([], "https://blog.naver.com/doctoronhr")


def test_tistory_paths():
    assert g8.tistory_paths("https://doctoronhr.tistory.com/11") == ["/11", "/m/11"]
    assert g8.tistory_paths("https://doctoronhr.tistory.com/m/8") == ["/8", "/m/8"]


def test_decide_naver_found_moves_state_and_logs():
    props, line = g8.decide(_post(), g8.Measure(7, 12, True), TODAY)
    assert props["색인 여부"]["select"]["name"] == "확인"
    assert props["상태"]["select"]["name"] == "색인확인"
    assert "조회수 D+7" not in props
    assert line == "11/03 G8 D+7(실측 D+12) 자동: 네이버 검색 노출 확인 · 조회 미측정(네이버 통계는 웅서 월요일)"


def test_decide_tistory_views_and_not_indexed():
    t = _post(no="T-001", channel="티스토리", url="https://doctoronhr.tistory.com/1")
    props, line = g8.decide(t, g8.Measure(7, 7, False, views=42, note="URL is unknown to Google"), TODAY)
    assert props["색인 여부"]["select"]["name"] == "안 잡힘"
    assert "상태" not in props and props["조회수 D+7"]["number"] == 42
    assert line.endswith("구글 미색인 · 조회 42 · URL is unknown to Google")
    early, _ = g8.decide(t, g8.Measure(3, 3, False, views=5), TODAY)
    assert early["색인 여부"]["select"]["name"] == "미확인" and "조회수 D+3" not in early


def test_decide_never_downgrades_or_touches_human_check():
    p = _post(index="확인", state="사람확인")
    props, line = g8.decide(p, g8.Measure(30, 30, False), TODAY)
    assert "색인 여부" not in props and "상태" not in props
    assert "안 나옴" in line
    failed, line2 = g8.decide(_post(), g8.Measure(7, 7, None), TODAY)
    assert failed == {} and "측정 실패" in line2


def test_from_row_skips_unpublished():
    row = {"id": "x", "properties": {
        "글 번호": {"type": "title", "title": [{"plain_text": "T-009"}]},
        "채널": {"type": "select", "select": {"name": "티스토리"}},
        "게시 URL": {"type": "url", "url": "https://doctoronhr.tistory.com/10"},
        "게시일": {"type": "date", "date": {"start": "2026-10-29"}},
        "상태": {"type": "select", "select": {"name": "게시완료"}},
    }}
    p = g8.from_row(row)
    assert p.no == "T-009" and p.published == date(2026, 10, 29) and not p.naver
    row["properties"]["게시 URL"]["url"] = None
    assert g8.from_row(row) is None


# --- 11/5 세현 결정 D-041 · D-026: 상태값 대조 · 정체 -------------------------- #
def _row(no, state, url="", day="", made="2026-11-03T05:00:00Z"):
    t = lambda s: {"type": "rich_text", "rich_text": [{"plain_text": s}] if s else []}
    return {"id": no, "created_time": made, "properties": {
        "글 번호": {"type": "title", "title": [{"plain_text": no}]},
        "상태": {"type": "select", "select": {"name": state}},
        "게시 URL": {"type": "url", "url": url or None},
        "게시일": {"type": "date", "date": {"start": day} if day else None},
        "제목": t("x")}}


def test_audit_flags_state_mismatch_and_stall():
    from datetime import datetime
    rows = [
        _row("N-001", "사람확인", "https://blog.naver.com/doctoronhr/1", "2026-10-22"),   # 공개됐는데 사람확인
        _row("T-003", "검수통과", "https://doctoronhr.tistory.com/6", "2026-10-27"),      # 게시 기록 있는데 검수통과
        _row("N-010", "게시완료"),                                                       # 게시 이후 상태인데 URL 없음
        _row("N-013", "근거수집", made="2026-11-03T07:21:57Z"),                         # 이틀째 정체
        _row("N-014", "근거수집", made="2026-11-05T05:00:00Z"),                         # 오늘 만든 행은 정상
        _row("T-008", "색인확인", "https://doctoronhr.tistory.com/8", "2026-10-28"),      # 정상
    ]
    out = g8.audit(rows, datetime(2026, 11, 5, 11, 0))
    text = "\n".join(out)
    assert "N-001" in text and "T-003" in text and "N-010" in text and "T-008" not in text
    assert "N-013" in text and "N-014" not in text
    assert sum(x.startswith("🔔") for x in out) == 2


def test_audit_clean_has_no_alert():
    from datetime import datetime
    out = g8.audit([_row("T-008", "색인확인", "https://doctoronhr.tistory.com/8", "2026-10-28")],
                   datetime(2026, 11, 5, 11, 0))
    assert out == []
