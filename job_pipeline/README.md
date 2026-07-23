# job_pipeline — 드래프트온 채용 수집·스코어링 파이프라인

`dashboard.html`(드래프트온 OPS 레이더)에 **실데이터**를 공급하는 백엔드.
채용 플랫폼에서 공고를 끌어와 통일 스키마로 정규화하고, 드래프트온 업로드
적합도와 헤드헌팅 리드 스코어를 매겨 대시보드용 JSON을 생성한다.

```
 수집(sources) → 정규화(normalize) → 스코어링(scoring) → 저장(store) → 공급(export)
   사람인 API        JobPosting        drafton_fit /       jobs.json      data/
   워크넷 API        (통일 스키마)      lead_score          (증분 병합)    dashboard.json
   원티드 크롤러
   sample(오프라인)                                           ↓
                                                    dashboard.html 이 fetch
```

## 빠른 시작 (오프라인, 자격증명 불필요)

```bash
cd <레포 루트>                       # 경로 기준은 레포 루트
pip install -r job_pipeline/requirements.txt   # 선택(표준 라이브러리만으로도 동작)
PYTHONPATH=job_pipeline python -m pipeline.cli run
# → data/dashboard.json 생성. 아래처럼 로컬 서버로 대시보드를 열면 실데이터 반영
python -m http.server 8000
#   http://localhost:8000/dashboard.html
```

> 대시보드는 `./data/dashboard.json` 을 `fetch` 한다. 파일이 없거나 `file://`
> 로 열어 CORS로 막히면 **내장 목업으로 자동 폴백**하므로 그냥 열어도 깨지지 않는다.
> 실데이터를 보려면 로컬/정적 서버(예: GitHub Pages)로 서빙할 것.

## 실데이터 소스 켜기

`.env.example` 을 `.env` 로 복사하고 키를 채운 뒤 `JOB_SOURCES` 에 소스를 추가한다.

| 소스 | 방식 | 필요 값 | 비고 |
|------|------|---------|------|
| `saramin` | 공식 Open API (JSON) | `SARAMIN_ACCESS_KEY` | https://oapi.saramin.co.kr |
| `worknet` | 공식 API (XML) | `WORKNET_AUTH_KEY` | 공공데이터포털/work.go.kr |
| `wanted` | 비공식 내부 JSON | `WANTED_CRAWLER_ENABLED=true` | ⚠️ ToS/robots 확인 후에만 |
| `sample` | 로컬 JSON | — | 오프라인 데모/테스트 기본값 |

```bash
JOB_SOURCES=saramin,worknet SARAMIN_ACCESS_KEY=xxx WORKNET_AUTH_KEY=yyy \
  PYTHONPATH=job_pipeline python -m pipeline.cli run
```

자격증명이 없는 소스는 **자동으로 건너뛴다**(에러 대신 skip). 전부 없으면 `sample`.

## CLI

| 명령 | 설명 |
|------|------|
| `sources` | 등록된 소스와 활성 여부 표시 |
| `collect` | 수집 → 스코어링 → 스토어(`job_pipeline/data/jobs.json`)에 증분 병합 |
| `export`  | 스토어 → `data/dashboard.json` 생성 |
| `run`     | `collect` + `export` 일괄 (크론 권장) |

주기 실행 예 (매시간):
```cron
0 * * * * cd /path/to/repo && PYTHONPATH=job_pipeline python -m pipeline.cli run
```

## 스코어링 기준 (핵심 IP)

- **drafton_fit (0~100)** = 스포츠 연관성(0~50) + 핵심 직무 매칭(0~30) + 독점성(0~20).
  70 이상이면 "업로드 권장". → `scoring.py::score_job`
- **lead_score (0~100)** = 채용 속도(0~40) + 시니어 비중(0~35) + 접근성(0~25).
  Hot/Warm/Nurture 티어로 분류. → `scoring.py::build_leads`
- **est_fee** = 시니어 수 × 섹터 단가 + 일반 포지션 가산 (만원).

가중치·임계값·키워드 사전은 모두 `scoring.py` / `taxonomy.py` 상단 상수로 모아
두었다. **운영하며 이 사전을 키우는 것이 정확도의 핵심** — 데이터가 아니라 판단
기준을 코드로 관리한다.

## 새 플랫폼 붙이기

1. `pipeline/sources/<플랫폼>.py` 에 `BaseSource` 를 상속해 `fetch()`(원천 dict
   목록)와 `normalize(raw)`(→ `JobPosting`) 구현. 마지막에 `self.enrich(job)` 호출로
   직무/섹터/규모를 자동 보강.
2. `pipeline/sources/__init__.py` 의 `_REGISTRY` 에 키 등록.
3. `JOB_SOURCES` 에 키 추가.

## 테스트

```bash
cd job_pipeline && python -m pytest -q     # 네트워크 불필요 (sample/순수 함수)
```

## 구조

```
job_pipeline/
  pipeline/
    models.py        통일 스키마 (JobPosting, CompanyLead)
    taxonomy.py      스포츠 키워드·직무/섹터/규모 사전
    scoring.py       drafton_fit / lead_score / est_fee
    normalize ↔ sources/base.py(enrich)
    store.py         JSON 스토어 + 증분 병합(워크플로 상태 유지)
    export.py        대시보드용 dashboard.json 생성
    collect.py       소스 오케스트레이션
    cli.py           sources/collect/export/run
    sources/         saramin · worknet · wanted · sample
  sample_data/raw_sample.json
  tests/test_pipeline.py
```
