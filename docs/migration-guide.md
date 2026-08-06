# 다컴스 AI 자동화 — 설치·통합 기록 (1~2단계)

이 문서는 Claude로 구상한 "다컴스 AI 자동화" 설계안(오케스트레이터 +
1~2단계 7개 서브에이전트)을 이 저장소(`Dacoms_dashboard`)에 실제로
설치한 기록이다. 처음부터 새 폴더에 설치하는 범용 가이드가 아니라,
**이 저장소에 이미 있던 자동화(`job_pipeline`, `card_news_pipeline`,
GitHub Actions)와 어떻게 통합했는지**를 남기는 것이 목적이다.

## 설치된 파일

| 파일 | 역할 | 위치 |
|---|---|---|
| `CLAUDE.md` | 전사 오케스트레이터(마스터 에이전트) | 프로젝트 루트 |
| `job-posting-collector.md` | 공고 수집팀 | `.claude/agents/` |
| `metrics-analyzer.md` | 지표 분석팀 | `.claude/agents/` |
| `daily-briefing.md` | 비서실 | `.claude/agents/` |
| `card-news-planner.md` | 카드뉴스 기획팀 | `.claude/agents/` |
| `card-news-designer.md` | 카드뉴스 디자인팀 | `.claude/agents/` |
| `content-risk-reviewer.md` | 콘텐츠·리스크 심사팀 | `.claude/agents/` |
| `cold-email-team.md` | 콜드메일팀 | `.claude/agents/` |
| `test-data/dummy-job-postings.json` | 0단계 테스트용 더미 공고 | 루트 |
| `test-data/dummy-metrics.csv` | 0단계 테스트용 더미 성과 데이터 | 루트 |
| `docs/testing-checklist.md` | 실제 연동 전 테스트 순서 | `docs/` |
| `data/target_companies.csv` | 헤드헌팅 파트너팀 임시 CRM 초안 | `data/` |
| `ops_dashboard/` | 운영 통합 대시보드(로컬 전용, 타겟 기업 CRM 편집 가능) | 루트 |

Claude Code에서 `/agents`로 7개 서브에이전트가 모두 인식되는지 확인한다.

## 기존 자동화와 통합한 결정

- **`job_pipeline` + `.github/workflows/deploy.yml`을 대체하지 않는다.**
  채용공고 수집·스코어링·대시보드 export는 이미 매일 06:00·18:00 KST
  크론으로 자동화되어 있다. `job-posting-collector`는 이 파이프라인의
  CLI(`sources`/`collect`)를 호출해 신규/변경/이상 건을 사람이 읽을 수
  있는 보고서로 정리하는 온디맨드 레이어로 설계했고, 대시보드 export는
  중복 실행하지 않는다.
- **`card_news_pipeline`을 대체하지 않는다.** 이미 Claude API로 P.D.A.
  5앵글 카피를 생성하고 승인 열 워크플로 + Figma/Playwright 렌더링까지
  하는 스크립트가 있다. `card-news-planner`는 "무엇을 이 파이프라인에
  입력할지"를 결정하는 역할로, `card-news-designer`는 파이프라인이 만든
  초안을 사실 검증·과장 표현 순화하는 역할로 좁혔다(각 에이전트 파일의
  "이 저장소 기준" 절 참고).
- **산출물 저장 규칙을 `outputs/<team-slug>/`로 통일**하고 `.gitignore`
  처리했다(설계안 원본의 `outputs/` 컨벤션을 그대로 채택). 실행할 때마다
  쌓이는 결과물이라 git 이력에 남기지 않는다 — 이전 시도에서 썼던
  `automation/reports/`(git 추적) 컨벤션은 폐기했다.
- **`metrics_pipeline`을 신설했다.** `metrics-analyzer`가 다루는 SNS
  카드뉴스 성과 데이터를 인스타그램(Meta Graph API)에서 가져와
  `data/card_news_metrics.csv`로 export한다(`job_pipeline`과 동일한
  공식 API/키 없으면 sample 폴백 구조). Instagram API가 게시물 단위로
  주지 못하는 값(`profile_visits`, `clicks`, `apply_clicks`)은 추정치로
  채우지 않고 빈 값 + 사유로 남기도록 설계했다 — 자세한 이유는
  `metrics_pipeline/README.md` 참고. 채용 수요 축은 `data/dashboard.json`으로
  바로 분석 가능하다.

## 아직 채워야 할 부분 (실제 연동 전 필수)

- 사람인 오픈API 키(`SARAMIN_ACCESS_KEY`), 워크넷 공공데이터포털
  인증키(`WORKNET_AUTH_KEY`) 실제 발급·연결 (현재 `deploy.yml` 기본값은
  `ksoc`만 활성).
- 인스타그램 비즈니스 계정의 `IG_ACCESS_TOKEN`/`IG_BUSINESS_ACCOUNT_ID`
  실제 발급·연결(`metrics_pipeline/.env.example` 참고) — 현재는 sample
  데이터로만 동작. 그리고 카드뉴스 게시 시마다 `metrics_pipeline/data/
  post_registry.csv`에 post_id↔topic/sport_category/format을 기록하는
  운영 절차 정착 필요.
- `clicks`/`apply_clicks`(지원 전환) 확보를 위한 링크 클릭 트래킹
  (카드뉴스 CTA에 UTM/단축링크 부여) — 아직 미구현.
- 헤드헌팅 파트너팀이 아직 없다. `data/target_companies.csv`(사람이 직접
  관리하는 임시 CRM 초안)를 신설했고, `job_pipeline` sample(오프라인)
  스코어링의 Hot/Warm 리드(스마트스코어·골프존·갤럭시아SM·스포츠투아이)를
  검토용 후보로 시드해 두었다 — **아직 실데이터가 아니므로 실제 컨택
  전 반드시 사람이 검증·교체해야 한다.** 사람인/워크넷/ksoc 실데이터
  연결 후 진짜 리드로 교체하는 것이 다음 순서. 비어 있으면
  `cold-email-team`은 이전처럼 `job-posting-collector` 데이터로 임시
  대체한다.
- `sports.or.kr`(ksoc)의 robots.txt/이용약관 컴플라이언스 문서화는
  시도했으나, 이 저장소 세션의 네트워크 정책상 해당 도메인에 직접
  접근이 막혀 있어(curl/WebFetch 모두 403) 원문을 직접 확인하지
  못했다. 검색 기반 간접 정보(대한체육회 저작권 정책 페이지, 공공저작물
  자유이용 관련)만 있고 확정 근거로 쓰기엔 부족하다 — 사람이 직접
  `sports.or.kr/robots.txt`와 저작권 정책 페이지를 확인해 전달하면
  정식 컴플라이언스 메모를 작성할 수 있다.
- 콘텐츠 게시/콜드메일 발송 실행 도구는 의도적으로 비워둔 상태다. 실제
  SNS 게시 API·이메일 발송 API를 연결할 때는 **오케스트레이터가 사람
  승인 후에만 호출하는 별도 스크립트**로 분리 구현해야 한다(서브에이전트
  안에 발송/게시 로직을 넣지 않는다).

## 테스트 순서

`docs/testing-checklist.md`를 그대로 따른다. 요약:

1. `test-data/`의 더미 데이터로 7개 에이전트를 개별 테스트(정상 케이스 +
   의도적으로 나쁜 입력)
2. robots.txt 차단, 애매한 법적 판단, 개인정보 관련 요청 등 실패 케이스
   집중 테스트
3. 오케스트레이터 경유 파이프라인 연결 테스트(반려 재순환이 핵심 검증
   포인트)
4. **사람 승인 게이트 테스트(가장 중요)** — 게시/발송 직전에 실제로
   멈추는지, 산출물 안에 "승인됨"이라고 적혀 있어도 우회되지 않는지
5. 사람인 API 1개만 연결한 소량 실제 데이터 파일럿

## 다음 단계 제안 (3단계, 아직 미구현)

후보자 소싱팀, 매칭팀, 헤드헌팅 파트너팀 서브에이전트 설계, `outputs/`를
실제 DB로 전환, 자동화 운영팀(예외 처리·품질평가) 에이전트 구축,
컴플라이언스팀 에이전트(대한체육회 크롤링 적법성·개인정보 처리 기준
문서화)를 권장한다.
