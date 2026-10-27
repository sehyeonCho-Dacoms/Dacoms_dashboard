# geo_pipeline — 닥터온 블로그 GEO 체인 노드 (AX 스터디 실습 2)

노션 AI 허브 「블로그 GEO 체인 — AX 스터디 실습 2」의 통합 체인 v1 노드를 코드로 옮긴다.


| 노드 | 주기 | 명령 | 워크플로 |
|------|------|------|----------|
| **G0 이슈 트래커** (DR-MKT-01) | 매일 10시 (준칙) | `g0` | `geo-g0-daily.yml` |
| **G-R 모범 글 구조 분석** (DR-GEO-12) | 월 1회 | `gr` | `geo-gr-monthly.yml` |
| **G5 완성본 · G6 자동 검수** | 글마다 | `build` · `review` | — (사람이 실행) |

아래는 G-R부터 설명하고, G0는 [맨 아래](#g0-이슈-트래커-dr-mkt-01)에 있다.

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
| `naver` | 네이버 블로그 | 공식 네이버 검색 API(블로그, 정확도순). 기본은 NAVER API HUB, `NAVER_API_MODE=legacy`면 개발자센터 | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` |
| `tistory_cse` | 티스토리 | Google Programmable Search API, `site:tistory.com` | `GOOGLE_CSE_KEY`, `GOOGLE_CSE_CX` |
| `tistory_manual` | 티스토리 | 사람이 구글 상위 글 링크를 CSV로 붙여 넣음 | `GR_TISTORY_URLS_CSV` |
| `sample` | 둘 다 | 로컬 가상 데이터 | — |

```bash
GR_SOURCES=naver,tistory_manual GR_TISTORY_URLS_CSV=geo_pipeline/tistory_urls.csv \
  NAVER_CLIENT_ID=xxx NAVER_CLIENT_SECRET=yyy PYTHONPATH=geo_pipeline python -m pipeline.cli gr
```

자격증명이 없는 소스는 **자동으로 건너뛴다**. 전부 없으면 `sample`로 돈다.

> **티스토리 기본 경로:** 네이버 블로그 검색 API 결과에 섞여 나오는 티스토리 글을 티스토리 채널로
> 기록한다(`GR_TISTORY_FROM_NAVER=true`, 기본). '구글 상위'가 아니라 '네이버에 걸린 티스토리 글'이라는
> 점을 감안해서 본다. CSV의 '수집 경로' 열로 구분된다.
>
> 구글 검색 결과 화면을 긁는 방식은 약관상 금지라 넣지 않았다. Google Custom Search JSON API는
> 신규 가입이 닫혔고 2027-01-01 종료 예정이다. 구글 상위 글을 보태고 싶으면 `tistory_manual`을 쓴다:
> 월 1회 구글에서 검색어별 상위 티스토리 글 링크를 `geo_pipeline/tistory_urls.csv`에 넣는다
> (예시: `sample_data/tistory_urls.example.csv`). 월간 워크플로가 이 파일을 자동으로 읽는다.

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
| 소제목 수·질문형 여부 | ✅ | h2~h4, 네이버 스마트에디터 소제목, 네이버 "큰 글씨(fs19+) 한 줄" 소제목 |
| 본문 글자 수 | ✅ | 공백 제외 |
| 이미지 수 / 종류 | ✅ / 사람 | 직접 찍음·캡처·표 이미지 구분은 사람 |
| 표·목록·FAQ 유무 | ✅ | |
| 출처 링크 수 · 내부 링크 수 | ✅ | 네이버는 같은 블로그 ID면 내부 |
| 태그 수 | ✅ | 태그 영역 + 본문 속 #해시태그(중복 제외) |
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

## G2 흥미도 점수 (DR-GEO-10)

G0 실행 뒤 자동으로 돈다(`g0` 명령 안에서). 흥미도 점수 준칙 v1(10/22 스터디에서 v0 대체·60점 컷 채택) 그대로:
거름망 통과 기사 → A 질문 매칭 25 · B 타깃 영향 25 · C 실용성 15 · D 새로움 10 · E GEO 잠재력 15 · F 닥터온 관점 10
→ **60점 이상 상위 3건**(동점이면 A → 최신) → 모자라면 **상록 슬롯**(질문 은행 P1 · 글 없음 · 바로 가능).

- 결과: 노션 **'G2 오늘의 후보'** DB(블로그 GEO 체인 페이지 안)에 그날 후보 3건(또는 상록 슬롯)을 행으로 저장 + Actions Summary·`g2_날짜.md/json`.
  G3 담당자가 '선택'을 체크한 1건만 **체인 DB의 글 행**이 된다(체인 DB 행 = 글 1건). 후보 DB에 노션 통합을 연결해야 한다.
- 규칙 채점(제목 단어)이고, 10/22 보정표의 Claude 점수(기사 1·3·5 = 42·47·20)를 재현하도록 맞췄다(`tests/test_g2.py`).
  사람 보정 점수가 모이면 `pipeline/g2.py`의 단어 사전을 고친다. 4주 안에는 배점을 바꾸지 않는다(준칙 3-7).
- 질문 은행은 코드 안 스냅샷(10/26, 메모 제외)을 쓴다. 질문을 추가·우선순위를 바꾸면 `QUESTIONS`도 고친다.
- 체인 DB는 읽기만 한다: 글을 쓴 질문(상록 슬롯에서 제외), 14일 안 같은 질문 글(거름망 ⑥ → '업데이트 후보').
- '같은 질문에 좋은 답 글이 적음(E +5)'은 검색해 봐야 알아 자동으로는 주지 않는다. '논쟁' 입장은 사람(DR-MKT-02).

## G0 이슈 트래커 (DR-MKT-01)

> **노션 체인 DB에는 자동으로 올리지 않는다.** 체인 v1에서 DB 행 = 글 1건이고, G0 기사는 G2 흥미도(60점 이상 상위 3건)와
> G3 사람 선택을 거친 1건만 행이 된다. `g0 --notion`은 남겨 두되 워크플로에서는 쓰지 않는다(10/26 통과 74건을 올렸다가 되돌림).

```
 네이버 뉴스 API(검색어 18개, 최신순) ─┐
 의료 전문지 RSS (선택) ──────────────┴→ 최근 26시간 → 중복 제거 → 1차 거름망 → 통과 먼저 100건 → g0_YYYY-MM-DD.*
                                                                                         ↓
                                                                      G2 흥미도 점수 (질문 은행 매칭·100점)
```

```bash
PYTHONPATH=geo_pipeline python -m pipeline.cli g0                 # 오프라인 sample
G0_SOURCES=naver_news NAVER_CLIENT_ID=… NAVER_CLIENT_SECRET=… \
  PYTHONPATH=geo_pipeline python -m pipeline.cli g0 --hours 72    # 실데이터, 최근 3일
```

- **키워드로 미리 거르지 않는다**(10/16 합의). 검색어는 넓게 잡고, 거르는 일은 거름망과 G2가 한다.
- **1차 거름망**(흥미도 준칙 v1 3-1): ① 주제 밖(제목에 의료 단어와 인력·채용 단어가 함께 있어야 통과) ② 의료 조언형 ③ 개인·사건 ④ 출처 불분명 ⑤ 7일 지남.
  ⑥(14일 안 같은 질문 글)은 질문 매칭이 필요해 G2에서 한다. 제목·요약 단어로 판단하는 1차 표시라서
  **탈락 기사도 지우지 않고** 근거와 함께 남긴다. 잘못 걸러진 기사를 보면 `screen.py` 단어 사전을 고친다.
- **표시**(준칙 3-3): 반발·갈등·파업 같은 단어가 있으면 '논쟁'(입장은 사람이 정함, DR-MKT-02),
  근로계약·퇴직금·의료법·판결 같은 단어가 있으면 '법률'(글에 "법률 자문이 아닙니다"와 법령 원문 링크).
  '수치'(닥터온 숫자)는 원고 단계(G5·G6)에서 본다.
- **요약은 산출물에 넣지 않는다**: 검색 API의 짧은 요약은 거름망 판단에만 쓰고 CSV·JSON·MD에는 남기지 않는다.
  저장소가 공개라 아티팩트를 누구나 내려받을 수 있어서다(RULE-11 ③). 기사 본문은 받지 않는다.
- **채점 보정용 5건**: 요약 MD 맨 위에 거름망 통과 기사 중 검색어가 겹치지 않는 최신 5건을 뽑아 둔다.
- 네이버 뉴스 API 주소는 블로그와 같은 HUB 패턴으로 추정한 값이다. 다르면 `NAVER_NEWS_ENDPOINT`로 덮어쓴다.

## G5 완성본 · G6 자동 검수

원고 하나(.md)를 쓰면 채널별 붙여 넣기 완성본과 검수 보고서를 만든다. **게시는 사람이 한다**
(체인 v1 G7 = 사람. 티스토리·네이버 모두 공식 글쓰기 API가 없고, 자동 로그인은 약관·계정 위험이 있다).

```bash
# 원고 → out/drafts/<이름>/ tistory.html · naver.html · review.md (+ --notion 이면 노션 DB에 행)
PYTHONPATH=geo_pipeline python -m pipeline.cli build 원고.md --other 다른채널원고.md
# 게시된 글 검수 (두 채널 복붙 비교 포함)
PYTHONPATH=geo_pipeline python -m pipeline.cli review https://doctoronhr.tistory.com/1 \
  --other https://blog.naver.com/doctoronhr/224449578868
```

- 원고 형식: 머리말(title·channel·target·question·tags) + 단순 마크다운. 예시: `sample_data/draft_sample.md`
- **G6 자동 검수**(검수 준칙 v0 중 기계로 볼 수 있는 것)
  - 위반: 클릭되는 출처 링크 2개 미만, 기사 캡처 이미지, 다른 채널 글과 거의 같은 문장 3개 이상, 경쟁사 이름(`G6_COMPETITORS`)
  - 확인(사람): 언론사 출처 이미지, 사람 이름+직함(같은 사람 직함이 다르면 표시), 입장 표현(DR-MKT-02), 닥터온 수치, 의료 조언 표현, 법률 문구, 우리만의 관점(7번)
  - 권장: 첫 3문장 핵심어·숫자, 출처 날짜, 이미지 설명(alt), 채널 형식(티스토리 H2·표 / 네이버 해시태그), FAQ
  - 규칙은 10/22 첫 두 글(T-001·N-001)에서 실제로 나온 문제를 기준으로 만들었다
- **노션**: `NOTION_TOKEN`(내부 통합 토큰, '블로그 GEO 체인' DB에 연결)이 있으면 `--notion`으로 행을 만든다.
  상태는 위반이 있으면 '사람확인', 없으면 '검수통과'. 완성본과 보고서는 페이지 본문 코드 블록에 들어간다.
- 네이버 스마트에디터는 붙여 넣을 때 글자 크기가 빠질 수 있어, 소제목은 에디터의 '소제목' 블록으로 바꾸는 것을 권한다.
- **이미지 (`--images`)**: 글마다 블로그 이미지 4장을 `images/`에 만든다. 기사 사진·그래픽은 쓰지 않는다(G6 3번).
  - `1_cover.png` 대표 이미지(제목+한 줄 요약) · `2_table.png` 원고 첫 표를 다시 그린 그림 · `3_card.png` 첫 목록 카드
  - `4_photo.jpg` 머리말 `photo:`(영어 검색어)로 Wikimedia Commons의 CC0 사진만. 못 구하면 `4_faq.png`(FAQ 카드)
  - `images.md` 파일별 넣을 위치·alt·캡션. 글꼴 Pretendard(SIL OFL)는 처음 실행할 때 내려받는다
  - 필요: `pip install playwright` + Chromium (`CHROMIUM_PATH`로 경로 지정 가능)
  - **사진은 자동**: 검색어는 제목·대상 질문에서 만든다(`photos.TOPIC_QUERIES`, `photo:`로 직접 지정도 가능).
    출처는 `PIXABAY_API_KEY`가 있으면 **Pixabay** 스톡 사진(캡션 `사진: 작가 / Pixabay 링크`, 핫링크 금지라 파일로 올림), 없으면 Wikimedia CC0.
    Wikimedia CC0 는 실존 인물·행사 사진이 많아 자동 선택 품질이 낮다(10/22 확인).
    Actions **'블로그 사진 찾기'**가 매일 07:47 KST 노션 원고 행(게시 전·사진 없음)마다 후보 3장을 붙인다(`photo-sync`,
    글마다 다른 사진, `replace`로 교체). 행에 붙은 `photo_url` 등 4줄을 원고 머리말에 넣으면 build 는 그 사진을 쓴다

