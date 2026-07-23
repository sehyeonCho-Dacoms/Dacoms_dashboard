# 카드뉴스 에이전트 (가이드북 2편 기반)

`@jay.pm.ai`의 "카드뉴스 에이전트 가이드북 2편"을 그대로 구현한 프로젝트입니다.
페르소나+욕구를 입력하면, Claude가 5가지 마케팅 앵글로 썸네일 카피를 쓰고,
본문 3장과 CTA를 작성하고, DALL-E로 배경 이미지를 생성해, 피그마에
완성된 카드뉴스 5장 세트를 자동으로 만들어줍니다.

```
페르소나+욕구 입력 → 썸네일 카피 생성(5앵글) → [승인] → 본문+CTA 작성
→ [승인] → DALL-E 이미지 생성 → 피그마 카드 완성
```

각 생성 단계는 **자기 검증 루프**를 거칩니다:

```
Claude 카피 생성 → Python 규칙 검증 → Claude 자기 평가 → 7점 이상? → 시트 저장
                                              │
                                     7점 미만이면 재작성(최대 3회)
```

---

## 프로젝트 구조

```
config.yaml              서비스 이름·설명·브랜드 레이블
.env                      API 키, 시트 URL (git 제외)
sheet_client.py           구글 시트 '카드뉴스 결과물' 22열 스키마 공용 클라이언트
verify_loop.py            규칙검증→자기평가→재작성 공용 루프
thumbnail_agent.py        5앵글 썸네일 헤드라인 생성 (공감/공포/이익/편의/사회증거)
body_agent.py             본문 3장(Card02~04) + CTA(Card05) 생성, 톤 일관성 검증
prompt_builder.py         헤드라인+페르소나 → DALL-E 프롬프트 (Claude Haiku 2단계)
image_agent.py            DALL-E 배경 생성 + 카드 배경 PNG 5장 렌더링(Playwright)
figma_agent.py            로컬 HTTP 서버(8765) — 플러그인에 카드 데이터 전달
pipeline.py                `pipeline.py serve` — 서버만 단독 실행
orchestrator.py           전체 파이프라인 오케스트레이션 (all --auto)
figma-plugin/             manifest.json, code.js — 마스터 프레임 복제·채우기
templates/background.html  DALL-E 원본 → 1080×1350 카드 배경 렌더링용 템플릿
tests/                    네트워크·키 없이 실행되는 단위 테스트
```

---

## 1. 설치

```bash
cd cardnews-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 2. API 키 / 시트 설정 (`.env`)

이 프로젝트는 아래 서비스 계정과 시트로 이미 설정되어 있습니다:

- 서비스 계정: `cardnewsbot@iron-ripple-503203-b3.iam.gserviceaccount.com`
- 대상 시트: `https://docs.google.com/spreadsheets/d/1ypNIPVZtBLOWqxZzKlFQTPoQKKHt44dgWD63q07tNhw/edit`

`.env`에 `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`는 이미 채워져 있습니다. **아직 남은 필수 작업:**

1. **서비스 계정 JSON 키 파일**을 프로젝트 루트에 `service_account.json`으로 저장하세요.
   (Google Cloud 콘솔 → IAM 및 관리자 → 서비스 계정 → `cardnewsbot@...` → 키 → 키 추가 → JSON)
2. 위 스프레드시트를 열고 **공유** → `cardnewsbot@iron-ripple-503203-b3.iam.gserviceaccount.com`을
   **편집자**로 추가하세요.
3. 시트 1행에 아래 22개 헤더가 있는지 확인하세요(없으면 첫 실행 시 자동 생성됩니다):
   `날짜, 폴더명, 페르소나, 욕구, 인지단계, 펀넬, 앵글, Card01 헤드라인, Card01 칩1, Card01 칩2,
   썸네일 상태, Card02 섹션타이틀, Card02 인풋텍스트, Card03 섹션타이틀, Card03 인풋텍스트,
   Card04 섹션타이틀, Card04 인풋텍스트, Card05 CTA 유도문구, 컨셉, 기대반응, 본문 상태, PNG 폴더`
4. (선택) K열(썸네일 상태)에 `썸네일 대기`/`썸네일 승인`, U열(본문 상태)에
   `본문 대기`/`본문 승인` 드롭다운을 설정해두면 수동 검토가 편해집니다.

## 3. 피그마 세팅

1. Figma Desktop에서 카드뉴스 파일을 엽니다.
2. 아래 4종류 마스터 프레임을 정확히 이 이름으로 만들어둡니다:
   `마스터_썸네일`, `마스터_본문_1`, `마스터_본문_2`, `마스터_CTA`
   (텍스트 레이어 순서와 배경 규칙은 가이드북 3-1~3-3절 참고)
3. 상단 메뉴 `Plugins → Development → Import plugin from manifest...` →
   `figma-plugin/manifest.json` 선택.

## 4. 실행

```bash
# 완전 자동 (승인 단계 없이 끝까지)
python3 orchestrator.py all --persona "20대 대학생" --desire "AI를 어떻게 더 잘 활용해야 할까?" --awareness problem-aware --auto

# 수동 검토 모드 (각 단계마다 시트에서 승인 후 Enter)
python3 orchestrator.py all --persona "20대 대학생" --desire "AI를 어떻게 더 잘 활용해야 할까?" --awareness problem-aware
```

`--awareness`: `unaware` | `problem-aware` | `solution-aware` | `product-aware`

마지막 단계에서 "Figma 플러그인 서버 시작" 메시지가 뜨면, Figma Desktop에서
`Plugins → Development → 카드뉴스 자동 생성`을 실행하세요. 카드가 자동
생성되고 완료되면 시트의 PNG 폴더 열이 `Figma 생성 완료`로 바뀝니다.
터미널에서 `Enter`를 누르면 서버가 종료됩니다.

### 개별 에이전트 단독 실행

```bash
python3 thumbnail_agent.py --persona "..." --desire "..." --awareness problem-aware [--auto]
python3 body_agent.py [--auto]
python3 image_agent.py
python3 pipeline.py serve   # 피그마 서버만 단독 재실행
```

---

## 시트 상태값

| 값 | 의미 |
|---|---|
| 썸네일 대기 | 썸네일 에이전트가 카피를 생성해서 저장한 상태 |
| 썸네일 승인 | 사람(또는 --auto)이 승인. 본문 에이전트가 이 행을 읽어감 |
| 본문 대기 | 본문 에이전트가 본문을 생성해서 저장한 상태 |
| 본문 승인 | 사람(또는 --auto)이 승인. 이미지 에이전트가 이 행을 읽어감 |
| 이미지 생성 중 (PNG 폴더) | DALL-E 이미지 생성 중 (중복 실행 방지) |
| Figma 생성 완료 (PNG 폴더) | 피그마 플러그인에서 카드 생성 완료 |

## 테스트

```bash
python3 -m pytest tests/ -q   # 규칙 검증·자기평가 루프·시트 스키마 (API 키 불필요)
```

## 문제 해결

가이드북 6장(자주 묻는 질문)을 참고하세요. 이 프로젝트에서 자주 발생할 수 있는 것:

| 증상 | 확인할 것 |
|---|---|
| `서비스 계정 JSON 키 파일을 찾을 수 없습니다` | `service_account.json`을 프로젝트 루트에 저장했는지 |
| `gspread.exceptions.SpreadsheetNotFound` 유사 오류 | 시트를 서비스 계정 이메일과 공유했는지 |
| Claude 관련 400 에러(`credit balance too low`) | Anthropic 콘솔에서 크레딧 충전 |
| 피그마 플러그인 "서버 연결 실패" | `python3 pipeline.py serve` 를 먼저 실행했는지 |
| 마스터 프레임을 찾을 수 없습니다 | 피그마 파일에 정확한 이름의 마스터 프레임이 있는지 |
