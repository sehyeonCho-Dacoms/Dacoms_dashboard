"""G0 1차 거름망 — 흥미도 준칙 v1(제안) 3-1의 거름망 6개 중 기계로 판별할 수 있는 것.

제목·요약의 단어로만 판단하는 1차 표시다. 최종 판단은 G2 흥미도 점수(AI)와 사람이 한다.
그래서 탈락 기사도 지우지 않고 '탈락(번호·근거)'으로 남겨, 잘못 걸러진 기사를 찾을 수 있게 한다.

  ① 주제 밖           제목에 의료 단어가 없거나, 제목·요약에 인력·채용 단어가 없거나, 질병·치료·신약 기사
  ② 의료 조언형       증상·예방법·건강 관리 기사
  ③ 특정 개인·사건    수사·재판·사고 기사
  ④ 출처 불분명       루머·찌라시 표현
  ⑤ 7일 지난 뉴스
  ⑥ 14일 안 같은 질문(GQ)으로 쓴 글 → 질문 매칭이 필요해 G2에서 판단 (여기선 안 함)

단어 사전은 운영하며 키운다. 잘못 걸러진 기사를 보면 아래 목록을 고친다.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .models import SCREEN_DROP, SCREEN_PASS, Article

# ① 조건 1: 제목에 의료 단어가 하나는 있어야 한다 (요약만 보면 '의사를 밝혔다' 같은 말에 걸림)
MEDICAL_TITLE_TERMS = [
    "의사", "의료", "병원", "전공의", "전문의", "의대", "간호", "의협", "병협", "복지부", "수가",
    "공보의", "개원의", "봉직의", "페이닥터", "필수의료", "지역의료", "의정갈등", "응급실", "수련", "원무",
]
# ① 조건 2: 제목·요약에 인력·채용·근무·운영 단어가 하나는 있어야 한다
WORKFORCE_TERMS = [
    "의사", "전공의", "전문의", "의대", "의료인", "인력", "간호사", "원무", "행정직", "채용", "구인",
    "구직", "연봉", "임금", "급여", "인건비", "근무", "당직", "수련", "봉직", "개원", "공보의",
    "필수의료", "지역의료", "수가", "의료개혁", "의료 개혁", "병원 경영", "경영난", "이직", "사직",
    "복귀", "휴진", "파업", "의협", "병협", "의대 정원", "의대정원", "증원", "의정갈등", "의정 갈등",
]
# '의사'가 들어가도 의료와 무관한 말 — 판별 전에 지운다 (첫 실행에서 '~할 의사를 밝혔다'가 통과됨)
FALSE_FRIENDS = [
    "의사결정", "의사 결정", "의사소통", "의사표시", "의사 표시", "의사표현", "의사 표현", "의사표명",
    "의사 표명", "의사록", "의사봉", "의사일정", "의사진행", "의사당", "의사를 밝", "의사가 없", "의사가 있",
    "의사를 전달", "의사를 내비", "의사를 표",
]

OFF_TOPIC_TITLE = ["신약", "임상시험", "임상 3상", "임상3상", "치료제", "수술 성공", "신기술 도입", "효능", "환자 사례"]
ADVICE_TITLE = ["증상", "예방법", "건강 관리", "건강관리", "다이어트", "좋은 음식", "먹으면", "자가진단"]
INCIDENT_TITLE = ["구속", "기소", "체포", "혐의", "피의자", "피고인", "숨져", "숨진", "사망사고", "폭행", "성추행", "횡령", "압수수색"]
RUMOR_TITLE = ["루머", "찌라시", "카더라", "확인되지 않은"]

# 점수와 별도로 붙이는 표시 (3-3) — 사람이 입장 확인 (DR-MKT-02)
CONTROVERSY_TERMS = ["찬반", "반발", "갈등", "투쟁", "규탄", "성명", "집단행동", "파업", "휴진", "반대", "철회"]


def _hit(text: str, terms: list[str]) -> list[str]:
    return [t for t in terms if t in text]


def screen(article: Article, now: datetime) -> Article:
    title = article.title
    text = _strip_false(f"{title} {article.description}")
    reasons: list[str] = []

    off = _hit(title, OFF_TOPIC_TITLE)
    if not _hit(_strip_false(title), MEDICAL_TITLE_TERMS):
        reasons.append("① 주제 밖(제목에 의료 단어 없음)")
    elif not _hit(text, WORKFORCE_TERMS):
        reasons.append("① 주제 밖(인력·채용 단어 없음)")
    elif off and not _hit(_strip_false(title), WORKFORCE_TERMS):
        reasons.append(f"① 주제 밖({'·'.join(off)})")
    if hit := _hit(title, ADVICE_TITLE):
        reasons.append(f"② 의료 조언형({'·'.join(hit)})")
    if hit := _hit(title, INCIDENT_TITLE):
        reasons.append(f"③ 개인·사건({'·'.join(hit)})")
    if hit := _hit(title, RUMOR_TITLE):
        reasons.append(f"④ 출처 불분명({'·'.join(hit)})")
    if article.published and now - article.published > timedelta(days=7):
        reasons.append("⑤ 7일 지남")

    article.screen = SCREEN_DROP if reasons else SCREEN_PASS
    article.screen_reasons = reasons
    article.flags = ["논쟁"] if _hit(text, CONTROVERSY_TERMS) else []
    return article


def _strip_false(text: str) -> str:
    for ff in FALSE_FRIENDS:
        text = text.replace(ff, "")
    return text


_SPACE = re.compile(r"\s+")


def title_key(title: str) -> str:
    """같은 기사 다른 매체 재전송을 묶기 위한 제목 키 (괄호 머리말·공백·문장부호 제거)."""
    t = re.sub(r"^\s*[\[\(【<][^\]\)】>]{0,12}[\]\)】>]\s*", "", title)
    return re.sub(r"[^\w]", "", _SPACE.sub("", t))
