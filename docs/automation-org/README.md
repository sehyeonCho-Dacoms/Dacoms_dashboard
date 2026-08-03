# 다컴스 자동화 조직 설계안 — 1단계 구현 기록

이 문서는 Claude를 통해 구상된 "다컴스 자동화 조직 설계안(v2.0)" 1단계
로드맵을 이 저장소에 실제로 설치한 기록이다. 원본 설계 초안(3개 팀
서브에이전트 + 오케스트레이터 안내)을 바탕으로, 이 저장소의 기존 자동화
(`job_pipeline`, `.github/workflows/deploy.yml`)와 충돌하지 않도록 통합했다.

## 설치된 파일

| 파일 | 역할 | 위치 |
|---|---|---|
| `CLAUDE.md` | 전사 오케스트레이터(마스터 에이전트) | 프로젝트 루트 |
| `job-posting-collector.md` | 공고 수집팀 서브에이전트 | `.claude/agents/` |
| `metrics-analyzer.md` | 지표 분석팀 서브에이전트 | `.claude/agents/` |
| `daily-briefing.md` | 비서실 서브에이전트 | `.claude/agents/` |

`CLAUDE.md`는 서브에이전트가 아니라 **오케스트레이터** 역할이다. 직접
작업을 수행하지 않고, 3개 서브에이전트를 어떤 순서로 호출할지, 사람 승인이
필요한 항목을 언제 막을지만 담당한다. 실행 사이클(아침/저녁/주간)과 산출물
저장 규칙은 프로젝트 루트의 `CLAUDE.md`에 정의되어 있다.

## 사용 방법

- Claude Code에서 `/agents` 명령으로 3개 서브에이전트가 정상 인식되는지
  확인한다.
- 오케스트레이터에게 "오늘 아침 사이클 실행해줘"처럼 요청하면 `CLAUDE.md`의
  실행 순서(공고 수집 → 지표 분석 참고 → 비서실 브리핑)에 따라 서브에이전트를
  순서대로 호출한다.
- 각 팀의 산출물(JSON)은 `automation/reports/<team-slug>/`에 쌓인다.

## 기존 자동화와의 통합 결정

- 채용공고 수집·스코어링·대시보드 export는 이미 `job_pipeline` +
  `.github/workflows/deploy.yml`(매일 06:00·18:00 KST 크론)로 자동화되어
  있었다. `job-posting-collector` 서브에이전트는 이를 대체하지 않고,
  `job_pipeline`의 CLI(`sources`/`collect`)를 호출해 신규/변경/이상 건을
  사람이 읽을 수 있는 보고서로 정리하는 온디맨드 레이어로 설계했다.
- `metrics-analyzer`가 다루는 SNS 카드뉴스 성과 데이터는 이 저장소에
  아직 실데이터 소스가 없다(`card_news_pipeline`은 카피 생성·렌더링까지만
  담당). 채용 수요 축은 `data/dashboard.json`으로 바로 분석 가능하지만,
  콘텐츠 축은 실데이터 연결 전까지 표본 부족으로 표시하도록 명시했다.
- `daily-briefing`이 취합할 팀 산출물 저장소를
  `automation/reports/<team-slug>/latest.json` 규칙으로 확정했다.

## 아직 채워야 할 부분 (실제 연동 전 필수)

- `job-posting-collector`: 사람인 오픈API 키(`SARAMIN_ACCESS_KEY`),
  워크넷 공공데이터포털 인증키(`WORKNET_AUTH_KEY`)를 실제로 발급받아
  저장소 시크릿/환경변수에 연결 (현재 `deploy.yml` 기준 기본값은
  `ksoc`(대한체육회, 키 불필요)만 활성).
- `metrics-analyzer`: 드래프트온 SNS 성과 데이터를 가져올 실제 데이터
  소스(API/DB/CSV export)가 아직 없음 — 파이프라인 신규 구축 필요.

## 다음 단계 제안

1단계 3개 팀이 안정적으로 도는 것을 확인한 뒤, 2단계(카드뉴스
기획·디자인·심사팀, 콜드메일팀)로 확장하는 것을 권장한다. 2단계부터는
설계안의 **사람 승인 게이트**(카드뉴스 실제 게시, 콜드메일 실제 발송)를
서브에이전트가 아니라 오케스트레이터/사람 확인 단계에서 처리하도록
분리해서 설계해야 한다. `card_news_pipeline`의 "승인" 열 워크플로가 이미
그 승인 게이트의 초기 형태로 존재한다.
