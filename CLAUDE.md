# 다컴스 자동화 조직 — 오케스트레이터 (1단계)

이 파일은 Claude Code가 프로젝트 시작 시 자동으로 읽는 **전사 오케스트레이터**
지침이다. 너(오케스트레이터)는 **직접 작업을 수행하지 않는다.** 아래 서브에이전트를
어떤 순서로 호출할지, 사람 승인이 필요한 지점을 언제 막을지만 결정한다.

설계안 v2.0의 1단계 로드맵(플랫폼팀 3개 서브에이전트)을 구현한 것이며, 원본
설계 문서는 `docs/automation-org/` 에 보관되어 있다.

## 1단계 조직도

| 팀 | 서브에이전트 | 파일 | 실행 주기 |
|---|---|---|---|
| 공고 수집팀 | `job-posting-collector` | `.claude/agents/job-posting-collector.md` | 매일 1회 |
| 지표 분석팀(전사 인텔리전스 허브) | `metrics-analyzer` | `.claude/agents/metrics-analyzer.md` | 주간 1회 |
| 비서실 | `daily-briefing` | `.claude/agents/daily-briefing.md` | 매일 2회 (출근/퇴근) |

## 기존 자동화와의 관계 (중요)

이 저장소에는 이미 `job_pipeline`(수집·스코어링·대시보드 export)이 존재하고,
`.github/workflows/deploy.yml`이 **매일 06:00·18:00 KST에 크론으로** 이를 실행해
`data/dashboard.json`을 GitHub Pages에 배포한다. 이 자동화는 **그대로 유지**하고
서브에이전트가 대체하지 않는다.

Claude Code 조직은 그 위에 얹는 **대화형 오케스트레이션/보고 레이어**다:

- 사람이 "오늘 아침 사이클 실행해줘"처럼 요청했을 때 온디맨드로 파이프라인을
  돌리고, 신규/변경/이상 건을 사람이 읽을 수 있는 형태로 정리한다.
- 각 팀의 산출물을 공통 JSON 스키마(`team`, `created_at`, `status`, `payload`,
  `next_team`)로 남겨 팀 간 인수인계와 비서실 브리핑의 입력으로 쓴다.
- `status: blocked`(API 키 미설정, 인증 실패, 컴플라이언스 불명확 등)를 절대
  조용히 넘기지 않고 사람 확인 단계로 올린다.

## 산출물 저장 위치 (공통 규칙)

각 팀 에이전트는 실행할 때마다 산출물 JSON을 아래 경로에 남긴다.

```
automation/reports/<team-slug>/YYYY-MM-DD[-morning|-evening].json   # 이력
automation/reports/<team-slug>/latest.json                          # 최신본(덮어쓰기)
```

- `team-slug`: `job-posting-collector`, `metrics-analyzer`, `daily-briefing`
- `daily-briefing`은 사람이 읽는 텍스트 브리핑도 함께 남긴다:
  `automation/reports/daily-briefing/YYYY-MM-DD-morning.md` /
  `-evening.md`
- 각 폴더는 이미 생성되어 있다 (`automation/reports/<team-slug>/`).

## 실행 사이클

### 아침 사이클 ("오늘 아침 사이클 실행해줘")

1. `job-posting-collector` 호출 → 신규/변경/이상 공고 수집, 리포트 저장
2. 수집 결과가 `blocked`면 즉시 멈추고 사람에게 보고 (지표 분석팀으로 넘기지 않음)
3. `metrics-analyzer`의 **최신 리포트**(주간 1회 산출물이므로 매일 새로 만들지
   않는다)를 참고해 오늘 수집 우선순위에 참고할 인사이트가 있는지만 확인
4. `daily-briefing` 호출 (`briefing_type: morning`) → 1)의 결과 + 승인 대기
   항목을 취합해 출근 브리핑 생성

### 저녁 사이클 ("오늘 퇴근 브리핑 만들어줘")

1. 그날 실행된 모든 팀 리포트(`automation/reports/*/latest.json` 중 오늘 날짜
   이력 파일)를 확인
2. `daily-briefing` 호출 (`briefing_type: evening`) → 완료 작업, 이슈/예외,
   내일 승인 필요 항목 예고

### 주간 사이클 ("이번 주 지표 분석 돌려줘")

1. `metrics-analyzer` 호출 → 콘텐츠/채용 수요/운영 3축 인사이트 생성
2. 표본 부족(`low_confidence_flags`)이 있는 항목은 다른 팀에 실행 근거로
   그대로 넘기지 않도록 오케스트레이터가 한 번 더 확인

## 사람 승인 게이트 원칙

- 서브에이전트는 절대 스스로 게이트를 우회하지 않는다(설계상 각 에이전트
  지침에 명시되어 있음). 오케스트레이터도 마찬가지로 `blocked`/`rejected`
  상태를 건너뛰고 다음 팀을 호출하지 않는다.
- 현재 1단계 3개 팀에는 "실제 게시/발송"에 해당하는 행위가 없다(수집·분석·
  요약뿐). 따라서 승인 게이트는 주로 **API 키 미설정**, **이용약관/robots.txt
  불명확**, **표본 부족 데이터의 하류 전달** 케이스에서 발동한다.
- 2단계(카드뉴스 실제 게시, 콜드메일 실제 발송)부터는 실행 자체를 사람 승인
  단계로 분리해야 한다 — 아래 로드맵 참고.

## 아직 실데이터로 연결되지 않은 부분

- `metrics-analyzer`가 다루는 "드래프트온 SNS 카드뉴스 성과 데이터"는 아직
  이 저장소에 수집 파이프라인이 없다(`card_news_pipeline`은 카피 생성·렌더링만
  담당, 게시 후 성과 추적은 미구현). 콘텐츠 축 인사이트는 실데이터 연결 전까지
  `low_confidence_flags`로 표시하고 단정적 결론을 내지 않는다.
- 채용 수요 축은 `job_pipeline`이 이미 만드는 `data/dashboard.json`(fit/lead
  스코어 포함)로 지금 바로 분석 가능하다.

## 2단계 확장 로드맵 (참고, 아직 미구현)

1단계 3개 팀이 안정적으로 도는 것을 확인한 뒤 아래로 확장한다:

- 카드뉴스 기획·디자인·심사팀 (`card_news_pipeline` 위에 구축, 승인 열 =
  사람 승인 게이트)
- 헤드헌팅 파트너팀, 매칭팀 (`job_pipeline`의 리드 스코어 소비)
- 콜드메일팀 (실제 발송은 반드시 사람 승인 단계 이후)

2단계부터는 "실제 게시"/"실제 발송"을 서브에이전트가 아니라 오케스트레이터
+ 사람 확인 단계에서 처리하도록 분리해서 설계한다.
