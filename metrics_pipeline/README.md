# metrics_pipeline — 카드뉴스 성과 수집 파이프라인

`metrics-analyzer` 서브에이전트에 실데이터를 공급하는 백엔드. `job_pipeline`과
같은 구조(공식 API 우선, 키 없으면 자동 skip, 오프라인 sample 폴백)를 따른다.

```
수집(Instagram Graph API) → 정규화(CardNewsMetric) → 레지스트리 결합 → 저장(store) → export
                                                      (post_id→topic 매핑)      data/card_news_metrics.csv
                                                                                        ↓
                                                                        metrics-analyzer 가 읽음
```

## 빠른 시작 (오프라인, 자격증명 불필요)

```bash
cd <레포 루트>
pip install -r metrics_pipeline/requirements.txt   # 선택(표준 라이브러리만으로도 동작)
cp metrics_pipeline/sample_data/post_registry_sample.csv metrics_pipeline/data/post_registry.csv
PYTHONPATH=metrics_pipeline python -m pipeline.cli run
# → data/card_news_metrics.csv 생성 (metrics-analyzer 에이전트가 이 파일을 읽는다)
```

## 왜 "값이 비어 있는" 컬럼이 있는가 (중요 — 반드시 읽을 것)

metrics-analyzer가 기대하는 스키마(`test-data/dummy-metrics.csv`)에는
`impressions`, `profile_visits`, `clicks`, `apply_clicks` 컬럼이 있지만,
**Instagram Graph API는 이 값들을 게시물 단위로 신뢰성 있게 주지 않는다.**
이 파이프라인은 없는 데이터를 추정치로 채우지 않고 빈 값으로 남긴다 —
`data_gaps`(스토어 JSON 내부)에 사유가 함께 기록된다.

| 컬럼 | 상태 | 이유 |
|---|---|---|
| `reach`, `saves`, `shares` | ✅ 실데이터 | Graph API가 미디어 단위로 안정적으로 제공 |
| `impressions` | ⚠️ best-effort | 2024년 이후 다수 표면에서 폐지·"views"로 대체됨. 있으면 채우고 없으면 빈 값 |
| `profile_visits` | ⚠️ best-effort | `profile_activity` 지표를 시도하되, 계정/API 버전에 따라 아예 없을 수 있음. **계정 전체 프로필 방문수로 대체하지 않는다**(게시물 단위로 잘못 귀속시키는 것이 실제 노출/저장 수보다 더 나쁜 오류이기 때문) |
| `clicks`, `apply_clicks` | ❌ 미구현 | Instagram 자체 지표가 아님. UTM/bit.ly 같은 링크 클릭 트래킹을 카드뉴스 CTA 링크에 붙여야 확보 가능 — 아직 이 저장소에 없음 |

이 상태로도 `metrics-analyzer`는 정상 동작한다 — `reach`/`saves`/`shares`
기반 콘텐츠 축 분석은 실데이터로 가능하고, 나머지는 표본 부족이 아니라
"데이터 소스 없음"으로 정직하게 보고하도록 설계되어 있다.

## 실데이터 소스 켜기 (인스타그램)

1. Meta for Developers에서 앱 생성, 인스타그램 계정을 프로페셔널(비즈니스/
   크리에이터)로 전환 후 페이스북 페이지에 연결
2. `instagram_basic`, `instagram_manage_insights`, `pages_read_engagement`,
   `pages_show_list` 권한을 가진 장기 액세스 토큰 발급
3. `.env.example`을 `.env`로 복사하고 `IG_ACCESS_TOKEN`,
   `IG_BUSINESS_ACCOUNT_ID` 채우기
4. `METRICS_SOURCES=instagram`로 설정 후 실행

```bash
METRICS_SOURCES=instagram IG_ACCESS_TOKEN=xxx IG_BUSINESS_ACCOUNT_ID=yyy \
  PYTHONPATH=metrics_pipeline python -m pipeline.cli run
```

자격증명이 없으면 **자동으로 sample로 폴백**한다(에러 대신 skip).

## 게시물 메타데이터 레지스트리 (필수 운영 작업)

Instagram API는 게시물이 어떤 카드뉴스 기획/종목인지 모른다. 카드뉴스가
게시되면, 담당자가 `metrics_pipeline/data/post_registry.csv`
(`post_id,topic,sport_category,format`)에 해당 게시물의 Instagram media id를
직접 추가해야 `metrics-analyzer`가 종목/포맷별로 성과를 나눠 볼 수 있다.
미등록 게시물은 `export` 실행 시 경고로 표시되고, CSV에는 topic 등이 빈 값으로
남는다(임의 추측 금지).

`sample_data/post_registry_sample.csv`를 복사해 시작하면 된다.

## CLI

| 명령 | 설명 |
|------|------|
| `sources` | 등록된 소스와 활성 여부, 레지스트리 경로 표시 |
| `collect` | 수집 → 스토어(`metrics_pipeline/data/metrics.json`)에 증분 병합 |
| `export`  | 스토어 → `data/card_news_metrics.csv` 생성 |
| `run`     | `collect` + `export` 일괄 |

## 테스트

```bash
cd metrics_pipeline && python -m pytest -q     # 네트워크 불필요 (sample/순수 함수)
```

`test_normalize_media_never_fabricates_profile_visits` /
`test_normalize_media_never_fabricates_apply_clicks`는 이 파이프라인의 핵심
설계 원칙(추정치로 채우지 않기)에 대한 회귀 테스트다 — 이 두 테스트가 깨지면
스키마를 다시 확인할 것.

## 다음 단계

- `clicks`/`apply_clicks` 확보를 위한 링크 클릭 트래킹(카드뉴스 CTA에 UTM
  파라미터 또는 bit.ly 단축링크 부여 후 그 클릭 로그 연동) 구축
- GitHub Actions로 주간 자동 수집(`job_pipeline`의 `deploy.yml`과 동일 패턴)
  연결 — 인스타그램 토큰이 실제로 발급된 뒤 진행
