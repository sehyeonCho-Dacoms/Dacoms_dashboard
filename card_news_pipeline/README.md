# 카드뉴스 자동 생성 파이프라인 (Card News Auto Pipeline)

구글 시트에 **주제**와 **타겟 페르소나**만 입력하면(또는 Gemini로 아예 브레인스토밍부터),
Claude가 **P.D.A. 프레임워크**로 카피 5가지 앵글을 만들어 시트에 자동 기입합니다.
담당자가 **'승인'** 표기한 카피만 피그마 플러그인으로 임포트하거나(브랜드 템플릿 적용
카드 생성), Playwright로 카드뉴스 PNG를 자동 렌더링합니다.

```
(선택) 브리프 ─ plan ─▶ Gemini(기획) ─▶ 주제·페르소나 N개 ─▶ 주제입력 시트
                                                              │
구글 시트(주제·페르소나) ◀────────────────────────────────────┘
        │  generate
        ▼
Claude API ─ P.D.A. 5앵글 카피 ─▶ 시트 초안 탭 기입
        │  담당자 검토 후 '승인' 표기
        ▼
승인 카피만 ──┬─ export ─▶ figma_import.json ─▶ 피그마 플러그인 ─▶ 브랜드 카드 프레임
             └─ render ─▶ OpenAI 표지 이미지 + Playwright ─▶ 카드뉴스 PNG (1080×1350 ×5장)
```

- **입력**: 구글 시트(주제, 타겟 페르소나) — 직접 입력하거나 Gemini로 기획 브레인스토밍
- **처리 0** (선택): Gemini API로 브랜드 브리프 → 주제·페르소나 조합 기획
- **처리 1**: Claude API로 P.D.A. 기반 카피 5앵글 생성
- **처리 2**: 생성 카피를 시트에 자동 기입 → 담당자 '승인' 표기
- **처리 3**: 승인 카피만 피그마 플러그인 임포트 / 이미지·카드 렌더링
- **출력**: 브랜드 템플릿이 적용된 카드뉴스 파일

요구 스택: **Python 3.10+ · Anthropic API · OpenAI API · Google Gemini API(선택) · Playwright**

---

## P.D.A. 프레임워크

본 파이프라인은 P.D.A.를 다음과 같이 정의합니다 (`copywriter.py`에서 프롬프트로 명시):

| 단계 | 의미 | 카드 |
|------|------|------|
| **P** — Problem | 페르소나가 겪는 문제·불편·결핍을 짚음 | 2번 카드 |
| **D** — Desire  | 문제가 해결된 이상적 모습·이득·변화를 그림 | 3번 카드 |
| **A** — Action  | 그 변화를 위한 구체적 다음 행동 제시 | 4번 카드 |

한 주제당 서로 관점이 다른 **5개 앵글**(예: 공감형·정보형·위기감형·혜택강조형·스토리텔링형)을
생성하며, 각 앵글은 `표지(후킹) → P → D → A → CTA` 5장으로 구성됩니다.
> P.D.A. 정의와 앵글 스타일은 `pipeline/copywriter.py`의 프롬프트를 수정해 조정할 수 있습니다.

---

## 설치

```bash
cd card_news_pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium        # 렌더링에 크로미움 필요
cp .env.example .env               # 키·설정 입력
```

`.env` 주요 값:

| 변수 | 설명 |
|------|------|
| `SHEET_BACKEND` | `local`(CSV, 개발용) 또는 `google`(실제 구글 시트) |
| `ANTHROPIC_API_KEY` | Claude API 키 (필수, generate 단계) |
| `OPENAI_API_KEY` | OpenAI 이미지 키 (선택; 없으면 브랜드 그라디언트 배경) |
| `GEMINI_API_KEY` | Google Gemini 키 (선택, plan 단계 — 기획/브레인스토밍) |
| `GOOGLE_SERVICE_ACCOUNT_JSON`, `SPREADSHEET_ID` | 구글 시트 백엔드용 (Gemini와는 별개) |
| `BRAND_*`, `CARD_WIDTH/HEIGHT` | 브랜드 템플릿 |

---

## 사용법

### 0) 초기화 (헤더 생성 + 로컬 샘플 시드)

```bash
python -m pipeline.cli --backend local init
```

### 0-b) (선택) 기획 — Gemini로 주제·페르소나 브레인스토밍

주제를 직접 입력하는 대신, 브랜드/서비스 브리프만 주고 Gemini가 주제·타겟 페르소나
조합을 여러 개 기획해 주제입력 시트에 채워 넣게 할 수 있습니다.

```bash
python -m pipeline.cli --backend local plan --brief "중소기업용 회계 자동화 SaaS" --count 5
```
`GEMINI_API_KEY`가 필요합니다(`.env` 참고). 기존 주제와 중복되지 않도록 시트의
기존 주제 목록을 함께 참고해 기획합니다.

### 1) 카피 생성 — 주제 → Claude P.D.A. 5앵글 → 초안 시트

```bash
python -m pipeline.cli --backend local generate
```

### 2) 검토 & 승인

초안 시트(로컬: `sample_data/drafts.csv`, 구글: `카피초안` 탭)의 **`승인`** 열에
`승인`(또는 `O`, `approved` 등)을 표기합니다.

### 3-a) 피그마 임포트용 내보내기

```bash
python -m pipeline.cli --backend local export       # output/figma_import.json 생성
```
피그마에서 플러그인 실행 → `figma_import.json` 내용을 붙여넣으면 승인 카피별로
브랜드 카드 프레임 5장씩 생성됩니다. (`figma-plugin/` 참고)

### 3-b) 카드 PNG 렌더링

```bash
python -m pipeline.cli --backend local render               # 이미지 포함
python -m pipeline.cli --backend local render --no-image    # 그라디언트 배경만
```
`output/`에 `<주제>_<앵글>_01~05.png` (1080×1350) 저장.

---

## 구글 시트 연동

이 프로젝트는 아래 서비스 계정으로 연동하도록 구성합니다:

```
cardnewsbot@iron-ripple-503203-b3.iam.gserviceaccount.com
```

1. **키 파일 준비**: GCP 콘솔(IAM 및 관리자 → 서비스 계정 → `cardnewsbot@...`)에서
   **키 추가 → JSON**으로 새 키를 발급받아 `service_account.json`으로 저장합니다.
   (기존 키가 있으면 재사용해도 됩니다. 키는 절대 깃허브에 커밋하지 마세요 — `.gitignore`에 이미 제외되어 있습니다.)
2. **시트 공유**: 연동할 구글 스프레드시트를 열고 **공유** → 위 이메일 주소를
   **편집자(Editor)** 권한으로 추가합니다.
3. **API 활성화**: 해당 GCP 프로젝트(`iron-ripple-503203-b3`)에서
   **Google Sheets API**와 **Google Drive API**를 사용 설정합니다.
4. **`.env` 설정**:
   ```env
   SHEET_BACKEND=google
   GOOGLE_SERVICE_ACCOUNT_JSON=./service_account.json
   SPREADSHEET_ID=<스프레드시트 URL의 /d/ 와 /edit 사이 값>
   ```
5. **연동 점검**:
   ```bash
   python -m pipeline.cli --backend google check
   ```
   서비스 계정 이메일, 시트 제목, 탭 목록이 출력되면 정상입니다. 실패하면
   1)~3) 단계(공유·API 활성화·`SPREADSHEET_ID`)를 다시 확인하세요.
6. 이후 `generate`/`export`/`render`를 `--backend google`(또는 `.env`의
   `SHEET_BACKEND=google`)로 실행하면 이 시트에 직접 기입/조회합니다.

시트 구성(첫 실행 시 자동 생성):
- **주제입력** 탭: `ID | 주제 | 타겟페르소나 | 상태`
- **카피초안** 탭: `주제ID | 주제 | 페르소나 | 앵글명 | 앵글설명 | 후킹 | 문제(P) | 욕망(D) | 행동(A) | CTA | 이미지프롬프트 | 승인`

---

## 피그마 플러그인

`figma-plugin/` — 피그마 데스크톱 앱에서 **Plugins → Development → Import plugin from manifest**로
`manifest.json`을 불러온 뒤 실행합니다. UI에 `export`로 만든 JSON을 붙여넣으면
승인 카피마다 `cover / P / D / A / CTA` 5개 프레임을 브랜드 색상으로 생성합니다.
(글꼴은 피그마 기본 `Inter` 사용)

---

## 아키텍처

```
pipeline/
  config.py       환경변수·브랜드 설정
  models.py       Topic / CopyAngle 데이터 구조
  sheets.py       Local(CSV) / Google(gspread) 백엔드 (동일 인터페이스)
  planner.py      Gemini API — 주제·페르소나 기획(브레인스토밍), 선택 단계
  copywriter.py   Claude API — P.D.A. 5앵글 (structured output)
  imagery.py      OpenAI 이미지 — 표지 배경 (실패 시 그라디언트 대체)
  renderer.py     Playwright — 브랜드 HTML → 카드 PNG
  templates/card.html   브랜드 카드 템플릿(Jinja2)
figma-plugin/     피그마 임포트 플러그인 (manifest/ui/code)
tests/            네트워크·키 없이 실행되는 단위 테스트
```

- **모델**: 기본 `claude-opus-4-8`, adaptive thinking + structured output(Pydantic 스키마)로
  파싱 안정성을 확보합니다. (`CLAUDE_MODEL` 로 변경 가능)
- **백엔드 추상화**: `local`(CSV)로 키·네트워크 없이 전체 흐름을 테스트할 수 있습니다.
- **견고성**: 이미지 생성 실패는 파이프라인을 멈추지 않고 브랜드 그라디언트로 대체합니다.

## 테스트

```bash
python -m pytest -q      # 시트 백엔드·모델 로직 (API 키 불필요)
```
