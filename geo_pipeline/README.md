# geo_pipeline — 닥터온 블로그 GEO 체인 노드 (AX 스터디 실습 2)

노션 AI 허브 「블로그 GEO 체인 — AX 스터디 실습 2」의 통합 체인 v1 노드를 코드로 옮긴다.
첫 노드는 **G-R 모범 글 구조 분석 (DR-GEO-12)** 이다.

```
 검색어 15개(+수식어) → 채널별 상위 5개 목록 → (허용 시) 글 구조 측정 → 글별 기록 + 형식 요약
   keywords.py          naver (검색 API)        structure.py              out/gr_YYYY-MM.csv/json
                        tistory_cse / _manual   본문 저장 없이 지표만      out/gr_YYYY-MM_summary.md
                                                                                 ↓
                                              허브 '원고 형식(타깃 2 × 채널 2)' 표 갱신 → G5 원고 · G6 검수
```

- 목적: 인기 글의 **내용이 아니라 구성**을 배운다. 본문은 저장하지 않고 구조 지표와 링크만 남긴다.
- 주기·담당: 월 1회 · AI+사람 (수집 담당 제안: 서웅서 / 기록 항목 정리: Claude)

## 빠른 시작 (오프라인, 자격증명 불필요)

```bash
cd <레포 루트>
pip install -r geo_pipeline/requirements.txt   # 선택(표준 라이브러리만으로도 동작)
PYTHONPATH=geo_pipeline python -m pipeline.cli gr
# → geo_pipeline/out/gr_YYYY-MM.{json,csv} + gr_YYYY-MM_summary.md
```

`sample` 소스는 `sample_data/`의 **가상** 검색 결과와 가상 HTML을 쓴다. 실제 글이 아니다.

## 실데이터 소스 켜기

`.env.example`을 `.env`로 복사해 키를 채우고 `GR_SOURCES`에 소스를 넣는다.

| 소스 | 채널 | 방식 | 필요 값 |
|------|------|------|---------|
| `naver` | 네이버 블로그 | 공식 네이버 검색 API(블로그, 정확도순) | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` |
| `tistory_cse` | 티스토리 | Google Programmable Search API, `site:tistory.com` | `GOOGLE_CSE_KEY`, `GOOGLE_CSE_CX` |
| `tistory_manual` | 티스토리 | 사람이 구글 상위 글 링크를 CSV로 붙여 넣음 | `GR_TISTORY_URLS_CSV` |
| `sample` | 둘 다 | 로컬 가상 데이터 | — |

```bash
GR_SOURCES=naver,tistory_manual GR_TISTORY_URLS_CSV=geo_pipeline/tistory_urls.csv \
  NAVER_CLIENT_ID=xxx NAVER_CLIENT_SECRET=yyy PYTHONPATH=geo_pipeline python -m pipeline.cli gr
```

자격증명이 없는 소스는 **자동으로 건너뛴다**. 전부 없으면 `sample`로 돈다.

> 구글 검색 결과 화면을 긁는 방식은 약관상 금지라 넣지 않았다. CSE 키가 없으면
> `tistory_manual`로 사람이 링크를 넣는다(CSV 예시: `sample_data/tistory_urls.example.csv`).

## 수집 기준 (RULE-11 외부 사이트 데이터 수집 기준)

| 준칙 | 코드에서 |
|------|----------|
| ① 이용약관·robots 확인 후 시작 | 글 페이지는 `GR_FETCH_PAGES=true`일 때만 연다(기본 꺼짐). 켜도 robots.txt가 막거나 robots를 못 읽으면 열지 않고 `robots 차단`으로 남긴다 |
| ② 개인 연락처 자동 수집 금지 | 수집 필드에 연락처 없음. 블로거 이름도 저장하지 않음 |
| ③ 원문 링크 중심, 본문 복제 금지 | `StructureRecord`에 본문 필드가 없음. 테스트가 산출물에 본문 문장이 없는지 확인 |
| 빈도 최소 | 요청 사이 `REQUEST_DELAY_SEC`(기본 2초). 월 1회 실행 |

`GR_FETCH_PAGES=false`면 목록(제목·링크·발행일·제목 패턴)만 자동으로 채우고, 구조 칸은
`사람 기록`으로 남는다. 허브 원안(“본문 구조는 사람이 열어 기록”)과 같은 방식이다.

## 글마다 기록하는 항목

| 허브 항목 | 자동 | 비고 |
|-----------|:---:|------|
| 제목 글자 수·패턴 | ✅ | 질문형·숫자·괄호·형식 수식어(총정리·비교·후기·하는 법·체크리스트·연봉표·Q&A) |
| 첫 2~3문장에 답이 있나 | △ | 첫 3문장의 글자 수, 검색어·숫자 포함 여부만 잰다. **실제로 답하는지는 사람이 확인** |
| 소제목 수·질문형 여부 | ✅ | h2~h4, 네이버 스마트에디터 소제목 |
| 본문 글자 수 | ✅ | 공백 제외 |
| 이미지 수 / 종류 | ✅ / 사람 | 직접 찍음·캡처·표 이미지 구분은 사람 |
| 표·목록·FAQ 유무 | ✅ | |
| 출처 링크 수 · 내부 링크 수 | ✅ | 네이버는 같은 블로그 ID면 내부 |
| 태그 수 | ✅ | |
| 작성자 소개 노출 · 공감·댓글 수 | 사람 | 스크립트로 늦게 그려져 자동으로 못 잰다 |
| 발행일 | ✅ | 네이버는 API `postdate`, 티스토리는 `article:published_time` |

블로그 스킨이 바뀌어 본문을 못 찾으면 `structure.py`의 `CONTENT_CLASSES`에 class 이름을 더한다.

## CLI

| 명령 | 설명 |
|------|------|
| `sources` | 등록된 소스와 활성 여부, 구조 측정 켜짐 여부 |
| `keywords` | 수집 검색어 목록 (`GR_WITH_MODIFIERS=true`면 2차 포함 120개) |
| `gr [--period YYYY-MM]` | G-R 실행 → `geo_pipeline/out/` |

## 검색어 바꾸기

`pipeline/keywords.py`의 `KEYWORD_GROUPS`가 허브 표와 같은 순서다. 허브 표를 고치면 여기도 같이 고친다.

## 테스트

```bash
cd geo_pipeline && python -m pytest -q
```
