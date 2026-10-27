"""G2 흥미도 점수 테스트 — 10/22 채점 보정표의 Claude 점수를 재현하는지 (네트워크 불필요)."""

from __future__ import annotations

from datetime import datetime, timedelta

from pipeline import g2
from pipeline.models import Article
from pipeline.sources.news import KST

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=KST)


def _a(title, hours=2, flags=(), i="x"):
    return Article(title=title, url=f"https://news.example/{i}", id=f"N-20261021-{i}", press="news.example",
                   published=NOW - timedelta(hours=hours), flags=list(flags))


def test_calibration_sheet_scores():
    # 보정표 기사 1·3·5 (기사 2·4는 G0 거름망 ①에서 탈락)
    s1 = g2.score(_a("'경북 국립의대' 국감서 잇단 촉구…국감 도마에 오르나", flags=["논쟁"]), NOW)
    assert (s1.a, s1.b, s1.c, s1.d, s1.e, s1.f, s1.total) == (15, 12, 0, 10, 5, 0, 42) and s1.gq.gq == 36
    s3 = g2.score(_a("\"상주 의사 0명\"…김윤덕, 이천 장애인선수촌 '의료 공백' 질타", flags=["논쟁"]), NOW)
    assert (s3.a, s3.b, s3.c, s3.d, s3.e, s3.f, s3.total) == (15, 12, 0, 10, 5, 5, 47) and s3.gq.gq == 31
    assert s3.target == "병원"
    s5 = g2.score(_a("비대면진료 처방일수 '30일 예외' 논란…의료계·플랫폼 대립", flags=["논쟁"]), NOW)
    assert (s5.a, s5.b, s5.c, s5.d, s5.e, s5.f, s5.total) == (0, 5, 0, 10, 5, 0, 20) and s5.gq is None
    assert s5.marks == ["논쟁"]


def test_direct_hiring_news_passes_cutoff():
    # 웅서님이 고른 N-005 주제와 같은 유형: 지방 의사 구인 + 월급 수치
    s = g2.score(_a("월급 3,300만 원에야 구한 신안군 의사, 시니어의사 지원사업 선정은 47%만"), NOW)
    assert s.total >= g2.CUTOFF and s.b == 25 and s.f == 10 and s.e == 10


def test_pick_cutoff_tie_and_update_candidate():
    hi = g2.score(_a("지방 병원 의사 연봉 공고 마감 앞두고 채용 몰려", i="1"), NOW)
    assert hi.total >= 60
    dup = g2.score(_a("지방 병원 의사 연봉 공고 마감 앞두고 채용 몰려", i="2"), NOW, recent_gq={hi.gq.gq: "T-009"})
    assert dup.update_candidate and "업데이트 후보(T-009)" in dup.marks
    low = g2.score(_a("비대면진료 논란", i="3"), NOW)
    assert g2.pick([low, dup, hi]) == [hi]


def test_evergreen_slots_skip_written_questions():
    slots = g2.evergreen_slots(3, written_gq={6, 15, 16, 25}, month=10)
    assert [q.gq for q in slots] == [20, 22, 30]
    assert all(q.priority == "P1" and q.ready == "바로 가능" for q in slots)
    assert g2.evergreen_slots(1, set(), month=1)[0].evergreen == "시즌"   # 1월엔 신규 전문의 시즌 질문 먼저


def test_run_g2_fills_with_evergreen_and_md_has_no_summary():
    arts = [_a("비대면진료 처방일수 '30일 예외' 논란", i="5")]
    arts[0].description = "요약 문장은 산출물에 넣지 않음"
    scores, top, slots = g2.run_g2(arts, NOW, written_gq={6, 15, 16, 25})
    assert not top and len(slots) == 3
    md = g2.summary_md(scores, top, slots, "2026-10-21")
    assert "상록 슬롯** GQ-20" in md and "요약 문장" not in md
    assert "A B C D E F" in md   # 준칙 3-5 출력 형식


def test_general_wage_news_is_not_our_target():
    # 10/27 오탐: 전체 근로자 임금 통계가 '월급'만으로 80점 1위
    s = g2.score(_a("임금근로자 절반 이상 월급 300만원 넘어…복지·의료 일자리 증가"), NOW)
    assert s.total < g2.CUTOFF and s.b == 5 and s.f == 0 and s.gq is None
    d = g2.score(_a("의사 평균소득 연 4억 돌파… 변호사 보다 3.8배 더 벌었다"), NOW)
    assert d.gq.gq == 39
