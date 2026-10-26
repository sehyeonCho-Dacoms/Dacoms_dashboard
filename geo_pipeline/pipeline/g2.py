"""G2 흥미도 점수·선별 (DR-GEO-10) — 흥미도 점수 준칙 v1 (10/22 스터디 채택: v1로 v0 대체 · 60점 컷).

  G0 거름망 통과 기사 → 6항목 100점 채점(A~F) → 60점 이상 상위 3건 → G3(사람 5분)
  60점 이상이 3건이 안 되면 질문 은행의 상록 슬롯으로 채운다(준칙 3-4).

채점은 제목·API 요약의 단어로 하는 규칙 채점이다. 기준 문장(준칙 3-2)을 단어 사전으로 옮겼고,
10/22 채점 보정표의 Claude 점수(기사 1·3·5: 42·47·20점)를 그대로 재현하도록 맞췄다(테스트).
사람 3명 보정 점수가 들어오면 사전을 고친다. 4주 안에는 배점을 바꾸지 않는다(준칙 3-7).

지키는 절대 준칙
  - 체인 DB('블로그 GEO 체인')의 행은 글 1건 → G2는 행을 만들지 않는다. 후보만 내고 G3 사람이 고른다
  - 논쟁 기사의 입장은 AI가 정하지 않는다(DR-MKT-02) → '논쟁' 표시만
  - RULE-11: 기사 본문을 받지 않고, 산출물에 요약을 넣지 않는다(제목·원문 링크만)
  - RULE-15·18: 닥터온 수치·정책 문구는 원고 단계에서 원장 확정값만 → 여기서는 '수치' 표시 대상 아님
  - 11/9 오픈 전: F(닥터온 관점)는 관점 연결만 보고, 링크는 원고(G5)에서 처리
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .models import SCREEN_PASS, Article

CUTOFF = 60
TOP_N = 3

# --------------------------------------------------------------------------- #
# 질문 은행 스냅샷 (노션 'GEO 질문 은행' 10/26 기준 · 질문 ID·우선순위·대상·채널·상록·준비도만, 메모 제외)
# (ID, 질문, 우선순위, 대상, 채널 적합, 상록성, 답 준비도, 기사 매칭 단어)
# --------------------------------------------------------------------------- #
@dataclass
class Question:
    gq: int
    text: str
    priority: str
    target: str
    channel: str
    evergreen: str
    ready: str
    terms: tuple[str, ...]

    @property
    def points(self) -> int:
        return {"P1": 25, "P2": 15, "P3": 8}.get(self.priority, 0)


QUESTIONS: list[Question] = [Question(*q) for q in [
    (1, "의사가 이직할 때 병원 정보를 어떻게 확인해?", "P2", "의사", "네이버", "상록", "근거 필요", ("병원 평판", "병원 정보")),
    (2, "닥터온은 어떤 서비스야?", "P1", "공통", "둘 다", "상록", "확정값 필요", ("닥터온",)),
    (3, "봉직의 연봉 정보는 어디서 확인할 수 있어?", "P1", "의사", "둘 다", "상록", "근거 필요", ("봉직의 연봉", "페이닥터 연봉", "의사 연봉 정보")),
    (4, "병원에서 의사를 빨리 채용하는 방법은?", "P1", "병원", "티스토리", "상록", "근거 필요", ("의사 채용", "의사 구인", "의사 모집")),
    (5, "의사 채용 수수료는 보통 얼마야?", "P1", "병원", "티스토리", "상록", "확정값 필요", ("채용 수수료", "소개 수수료")),
    (6, "의사 헤드헌팅과 매칭 플랫폼은 뭐가 달라?", "P1", "공통", "티스토리", "상록", "바로 가능", ("헤드헌팅", "매칭 플랫폼")),
    (7, "요즘 의료 인력 정책이 의사 채용 시장에 어떤 영향을 줘?", "P2", "공통", "티스토리", "뉴스 연동", "근거 필요", ("의료 인력", "의료인력", "필수의료", "의료개혁", "의료 개혁")),
    (8, "지방 병원 의사 채용 연봉은 서울보다 얼마나 높아?", "P2", "의사", "티스토리", "상록", "근거 필요", ("지방 병원 연봉", "지역 의사 연봉")),
    (10, "의사 구인구직 사이트 어디가 좋아?", "P1", "의사", "둘 다", "상록", "근거 필요", ("구인구직 사이트", "구인구직 플랫폼")),
    (11, "병원 원무과·행정직은 의사 채용을 어떻게 진행해?", "P1", "반의사", "네이버", "상록", "근거 필요", ("원무과", "원무 ")),
    (12, "병원 채용 공고는 어떻게 쓰면 지원자가 늘어?", "P2", "반의사", "네이버", "상록", "바로 가능", ("채용 공고", "구인 공고")),
    (13, "간호사가 병원 이직할 때 뭐부터 확인해야 해?", "P2", "반의사", "네이버", "상록", "바로 가능", ("간호사 이직", "간호사 채용", "간호 인력", "간호사 인력")),
    (14, "페이닥터 연봉은 진료과별로 얼마나 차이 나?", "P1", "의사", "티스토리", "상록", "근거 필요", ("진료과별", "과별 연봉", "진료과 연봉")),
    (15, "의사 연봉 계약에서 네트(세후)와 그로스(세전)는 뭐가 달라?", "P1", "의사", "둘 다", "상록", "바로 가능", ("네트", "세후 연봉")),
    (16, "봉직의 근로계약서에서 꼭 확인할 조항은?", "P1", "의사", "네이버", "상록", "바로 가능", ("근로계약", "계약서")),
    (17, "의사 퇴직금은 계약 형태에 따라 어떻게 달라져?", "P2", "의사", "티스토리", "상록", "근거 필요", ("퇴직금",)),
    (18, "당직비와 인센티브는 보통 어떻게 정해져?", "P2", "의사", "네이버", "상록", "근거 필요", ("당직비", "인센티브", "당직 수당", "당직수당")),
    (19, "사택이나 숙소를 주는 병원은 어떤 조건이 많아?", "P3", "의사", "네이버", "상록", "근거 필요", ("사택", "관사", "숙소")),
    (20, "현 직장에 알리지 않고 이직을 알아볼 수 있어?", "P1", "의사", "둘 다", "상록", "바로 가능", ("비공개 이직", "몰래 이직")),
    (21, "봉직의는 보통 언제 이직을 많이 해?", "P2", "의사", "네이버", "시즌", "근거 필요", ("이직 시기", "이직 시즌")),
    (22, "전문의 취득 후 첫 봉직 자리는 어떻게 구해?", "P1", "의사", "네이버", "시즌", "바로 가능", ("신규 전문의", "전문의 시험", "전문의 취득", "전문의 합격")),
    (23, "공보의를 마치고 봉직의로 갈 때 뭘 준비해야 해?", "P2", "의사", "네이버", "시즌", "바로 가능", ("공보의", "공중보건의")),
    (24, "개원과 봉직, 연차별로 뭐가 유리해?", "P2", "의사", "티스토리", "상록", "근거 필요", ("개원과 봉직", "개원 vs", "봉직 vs")),
    (25, "면접에서 들은 조건이 계약 때 바뀌면 어떻게 해?", "P1", "의사", "네이버", "상록", "바로 가능", ("조건 변경", "근로조건 변경", "채용 조건")),
    (26, "의사가 이직할 때 헤드헌터를 써야 할까?", "P2", "의사", "둘 다", "상록", "바로 가능", ("헤드헌터",)),
    (27, "이름을 밝히지 않고 병원 제안을 받을 수 있는 서비스가 있어?", "P1", "의사", "둘 다", "상록", "확정값 필요", ("익명 구직", "익명 이직")),
    (28, "의원에서 페이닥터를 구할 때 연봉은 얼마로 제시해야 해?", "P1", "병원", "티스토리", "상록", "근거 필요", ("페이닥터 구", "봉직의 구", "월급", "급여 제시")),
    (29, "지방 병원은 의사를 어떻게 구해야 해?", "P1", "병원", "둘 다", "상록", "근거 필요", ("지방 병원", "지역 병원", "농어촌", "도서 지역", "섬 지역", "군 의료원", "지방의료원", "지역의료원")),
    (30, "의사 채용이 막판에 무산되는 이유는 뭐야?", "P1", "병원", "티스토리", "상록", "바로 가능", ("채용 무산", "채용 취소")),
    (31, "의사 구인 공고를 계속 올려도 지원이 없으면 어떻게 해?", "P2", "병원", "네이버", "상록", "바로 가능", ("구인난", "지원자 없", "지원 없", "미달", "못 구해", "못 구한", "의료 공백", "공백")),
    (32, "의사 채용 성공보수 계약에서 확인할 조항은?", "P2", "병원", "티스토리", "상록", "바로 가능", ("성공보수",)),
    (33, "원무과에서 의사 면접 일정을 잡을 때 주의할 점은?", "P3", "반의사", "네이버", "상록", "바로 가능", ("면접 일정",)),
    (34, "병원 행정직은 어떤 일을 하고 어떻게 취업해?", "P2", "반의사", "네이버", "상록", "바로 가능", ("행정직", "병원 행정")),
    (35, "병원 인사 담당자는 의사 연봉 협상을 어떻게 준비해?", "P2", "반의사", "네이버", "상록", "근거 필요", ("연봉 협상",)),
    (36, "의대 정원 증원이 봉직의 채용 시장에 어떤 영향을 줘?", "P2", "공통", "티스토리", "뉴스 연동", "근거 필요", ("의대 정원", "의대정원", "증원", "국립의대", "의대 신설", "지역의대")),
    (37, "지역의사제는 지방 병원 의사 채용을 바꿀까?", "P2", "공통", "티스토리", "뉴스 연동", "근거 필요", ("지역의사제", "지역 의사제", "공공의대", "지역의사")),
    (38, "전공의 사직 이후 봉직의 시장은 어떻게 바뀌었어?", "P2", "공통", "티스토리", "뉴스 연동", "근거 필요", ("전공의 사직", "전공의 복귀", "사직 전공의", "전공의 이탈")),
    (39, "의사 연봉은 해마다 얼마나 올랐어?", "P2", "공통", "티스토리", "상록", "근거 필요", ("의사 연봉", "의사 평균 연봉", "의사 임금", "의사 소득")),
    (40, "닥터온 수수료는 얼마야?", "P2", "병원", "둘 다", "상록", "확정값 필요", ("닥터온 수수료",)),
    (41, "닥터온에 올린 내 정보는 어떻게 보호돼?", "P1", "의사", "둘 다", "상록", "확정값 필요", ("닥터온 개인정보",)),
    (9, "닥터온 임상 가치 설문은 뭐야?", "P3", "의사", "둘 다", "상록", "확정값 필요", ("임상 가치 설문",)),
]]
BY_ID = {q.gq: q for q in QUESTIONS}

# --------------------------------------------------------------------------- #
# 기준 문장 → 단어 사전 (준칙 v1 3-2)
# --------------------------------------------------------------------------- #
# B. 직접: 의사·병원·반의사의 채용·이직·근무 조건이 바로 바뀌거나 드러남
B_DIRECT = ("연봉", "월급", "임금", "급여", "수당", "당직비", "인건비", "채용", "구인", "모집", "구해", "구했", "구한",
            "근무 조건", "근무조건", "근무시간", "근무 시간", "처우", "계약", "이직", "퇴직금")
# B. 간접: 인력 공급·정책·시장 분위기
B_INDIRECT = ("정원", "증원", "의대", "지역의사", "공백", "부족", "인력", "전공의", "복귀", "사직", "필수의료",
              "수가", "의료개혁", "의료 개혁", "지역의료", "공보의", "수련")
SEMI_DOCTOR = ("간호", "원무", "행정직", "병원 행정", "의료기사", "보건직")
HOSPITAL = ("병원장", "의료원", "병원들", "병원이", "병원은", "병원 경영", "경영난", "구인난", "공백", "못 구")
# C. 실용성: 읽고 바로 할 일이 있음 / 알아두면 좋음
C_ACTION = ("신청", "모집", "접수", "마감", "시행", "지원사업", "공고", "계약", "개정안", "입법예고", "바뀐", "달라")
C_INFO = ("발표", "확정", "통과", "개정", "조사", "결과", "평균", "현황", "선정", "실태")
# E. 검색·AI 질문 수요가 큰 주제 (질문 매칭이 없어도)
E_DEMAND = ("비대면", "의대 정원", "의대정원", "전공의", "필수의료", "연봉", "지역의사")
E_FIGURE = re.compile(r"\d[\d,.]*\s*(?:만\s*원|억|원|%|퍼센트|배)")
# F. 닥터온 관점: 익명성 · 조건 고정 · 시세
F_DIRECT = ("익명", "비공개", "현 직장", "조건 변경", "약속과 다른", "처우", "계약", "연봉", "월급", "임금",
            "급여", "수당", "시세", "억")
F_INDIRECT = ("구인난", "공백", "부족", "못 구", "채용", "구인", "이직")


@dataclass
class Score:
    article: Article
    a: int = 0
    b: int = 0
    c: int = 0
    d: int = 0
    e: int = 0
    f: int = 0
    gq: Question | None = None
    target: str = "의사"
    marks: list[str] = field(default_factory=list)
    reason: str = ""
    update_candidate: bool = False   # 거름망 ⑥: 14일 안 같은 질문 글 있음

    @property
    def total(self) -> int:
        return self.a + self.b + self.c + self.d + self.e + self.f

    @property
    def channel(self) -> str:
        if not self.gq or self.gq.channel == "둘 다":
            return "둘 다"
        return self.gq.channel


def _has(text: str, terms) -> list[str]:
    return [t for t in terms if t in text]


def match_question(text: str) -> Question | None:
    hits = [q for q in QUESTIONS if _has(text, q.terms)]
    return max(hits, key=lambda q: (q.points, -q.gq)) if hits else None


def score(a: Article, now: datetime, recent_gq: dict[int, str] | None = None) -> Score:
    """기사 1건 채점. 제목을 우선 보고, 요약은 질문 매칭에만 보탠다(요약의 우연한 단어로 점수가 뛰지 않게)."""
    title = a.title
    s = Score(a, marks=[m for m in a.flags if m in ("논쟁", "법률")])

    q = match_question(title) or match_question(f"{title} {a.description}")
    if q:
        s.gq, s.a = q, q.points

    if _has(title, B_DIRECT):
        s.b = 25
    elif _has(title, B_INDIRECT):
        s.b = 12
    else:
        s.b = 5
    if _has(title, SEMI_DOCTOR):
        s.target = "반의사"
    elif _has(title, HOSPITAL) or (q and q.target == "병원"):
        s.target = "병원"
    elif q and q.target == "반의사":
        s.target = "반의사"

    s.c = 15 if _has(title, C_ACTION) else 8 if _has(title, C_INFO) else 0

    age = now - a.published if a.published else timedelta(0)
    s.d = 10 if age <= timedelta(hours=48) else 6 if age <= timedelta(days=4) else 3 if age <= timedelta(days=7) else 0

    s.e = (5 if (q or _has(title, E_DEMAND)) else 0) + (5 if E_FIGURE.search(title) else 0)
    # '같은 질문에 좋은 답 글이 적음 +5'는 검색해 봐야 알 수 있어 자동 채점에서는 주지 않는다(사람 확인)

    s.f = 10 if _has(title, F_DIRECT) else 5 if _has(title, F_INDIRECT) else 0

    if q and recent_gq and q.gq in recent_gq:
        s.update_candidate = True
        s.marks.append(f"업데이트 후보({recent_gq[q.gq]})")
    s.reason = _reason(s)
    return s


def _reason(s: Score) -> str:
    parts = []
    parts.append(f"GQ-{s.gq.gq}({s.gq.priority})에 답하는 재료" if s.gq else "맞는 질문 없음")
    parts.append({25: "채용·근무 조건에 직접", 12: "시장·정책 간접", 5: "타깃 영향 약함"}[s.b])
    if s.c == 15:
        parts.append("바로 할 일 있음")
    return " · ".join(parts)


def pick(scores: list[Score]) -> list[Score]:
    """60점 이상 · 업데이트 후보 제외 · 동점이면 A 높은 것 → 최신순, 상위 3건 (준칙 3-4)."""
    ok = [s for s in scores if s.total >= CUTOFF and not s.update_candidate]
    ok.sort(key=lambda s: (s.total, s.a, s.article.published.timestamp() if s.article.published else 0), reverse=True)
    return ok[:TOP_N]


def evergreen_slots(n: int, written_gq: set[int], month: int) -> list[Question]:
    """상록 슬롯: P1 · 아직 글 없음 · 답 준비도 '바로 가능', 시즌이 맞는 것 우선(준칙 3-4 3번)."""
    pool = [q for q in QUESTIONS if q.priority == "P1" and q.ready == "바로 가능" and q.gq not in written_gq]
    in_season = month in (12, 1, 2, 3)   # 신규 전문의·공보의 시즌 캠페인 (질문 은행 메모: Q1 시즌)
    pool.sort(key=lambda q: (not (in_season and q.evergreen == "시즌"), q.gq))
    return pool[:n]


def run_g2(articles: list[Article], now: datetime, written_gq: set[int] | None = None,
           recent_gq: dict[int, str] | None = None) -> tuple[list[Score], list[Score], list[Question]]:
    """(채점 전체, G3로 넘길 후보, 상록 슬롯)."""
    scores = [score(a, now, recent_gq) for a in articles if a.screen == SCREEN_PASS]
    scores.sort(key=lambda s: s.total, reverse=True)
    top = pick(scores)
    slots = evergreen_slots(TOP_N - len(top), written_gq or set(), now.month) if len(top) < TOP_N else []
    return scores, top, slots


def line(s: Score) -> str:
    """준칙 3-5 출력 형식."""
    a = s.article
    gq = f"GQ-{s.gq.gq}" if s.gq else "-"
    return (f"{a.id} | 통과 | {s.a} {s.b} {s.c} {s.d} {s.e} {s.f} | {s.total} | {s.target} | {gq} | {s.channel} | "
            f"{'·'.join(s.marks) or '-'} | {s.reason}")


def summary_md(scores: list[Score], top: list[Score], slots: list[Question], day: str) -> str:
    out = [f"# G2 흥미도 점수 — {day}", "",
           f"- 채점 {len(scores)}건(G0 거름망 통과) · {CUTOFF}점 이상 {sum(s.total >= CUTOFF for s in scores)}건"
           f" → G3 후보 {len(top)}건" + (f" + 상록 슬롯 {len(slots)}건" if slots else ""),
           "- 규칙 채점(제목 단어)입니다. 후보를 고르는 것은 G3 담당자 5분입니다. 체인 DB 행은 고른 1건만 만듭니다.",
           "- 뉴스형 글은 주 1편까지, 주 2편이면 의사 1 + 병원·반의사 1 (준칙 3-4). '논쟁'은 입장을 사람이 정합니다(DR-MKT-02).",
           "", "## G3로 넘길 후보", ""]
    if not top and not slots:
        out.append("- 없음")
    for i, s in enumerate(top, 1):
        a = s.article
        gq = f"GQ-{s.gq.gq} {s.gq.text}" if s.gq else "맞는 질문 없음 → 좋은 기사면 G1 새 질문 후보"
        out += [f"{i}. **{s.total}점** [{_md(a.title)}]({a.url}) · {a.press}",
                f"   - 타깃 {s.target} · 채널 {s.channel} · {gq}" + (f" · 표시 {'·'.join(s.marks)}" if s.marks else ""),
                f"   - A{s.a} B{s.b} C{s.c} D{s.d} E{s.e} F{s.f} · {s.reason}"]
    for j, q in enumerate(slots, len(top) + 1):
        out.append(f"{j}. **상록 슬롯** GQ-{q.gq} {q.text} · 대상 {q.target} · 채널 {q.channel}")
    out += ["", "## 채점 전체 (준칙 3-5 형식)", "", "```txt",
            "기사ID | 거름망 | A B C D E F | 총점 | 타깃 | 매칭 질문 | 채널 | 표시 | 한 줄 이유"]
    out += [line(s) for s in scores]
    out += ["```", ""]
    return "\n".join(out)


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("[", "(").replace("]", ")")
