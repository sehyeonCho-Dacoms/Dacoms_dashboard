# Instagram Insights Windows Connector

Windows PC에서 Instagram API(Instagram API with Instagram Login,
`graph.instagram.com`)에 연결해 프로필과 최근 콘텐츠의 조회수/도달/저장/공유 지표를
수집하는 PowerShell 스크립트 모음입니다.

> **실행 환경 안내**: 이 스크립트들은 Windows 전용입니다 (Windows Forms 입력창,
> DPAPI, 작업 스케줄러 사용). 실제 실행·연결 테스트는 사용자의 Windows PC에서
> 직접 수행해야 합니다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `InstagramConnector.Common.ps1` | 나머지 스크립트가 공유하는 함수 모음 (dot-source로 로드됨, 직접 실행하지 않음) |
| `setup-instagram-insights.ps1` | 최초 1회(또는 재설정 시) 실행. 자격 증명 입력 → DPAPI 암호화 저장 → 장기 토큰 교환 → 연결/권한 테스트 → 자동 갱신 예약 작업 등록 |
| `renew-instagram-token.ps1` | 만료 10일 이내일 때만 토큰을 갱신 (작업 스케줄러가 매일 자동 호출) |
| `collect-instagram-insights.ps1` | 프로필 + 최근 콘텐츠 5개 지표 수집, JSON/Markdown 저장 |
| `daily-instagram-brief.ps1` | 매일 오전 10시, 팔로워 수·증감과 최근 콘텐츠 성과를 요약한 브리프 생성 (작업 스케줄러가 자동 호출) |
| `enable-daily-brief.ps1` | 이미 설정을 마친 PC에서 위 브리프의 매일 10시 자동 실행만 추가로 등록 (토큰 재입력 불필요) |
| `diagnose-instagram-token.ps1` | 토큰 교환 없이 토큰 자체의 유효성만 단독으로 진단하는 보조 스크립트 |

## 사전 준비

- Meta 개발자 콘솔에서 **Instagram API with Instagram Login**으로 설정된 앱
- 이미 발급받은 Instagram 액세스 토큰(단기 또는 장기)과 앱 시크릿
- Windows 10/11, PowerShell 5.1 이상 (PowerShell 7의 경우 Windows에서만 동작)

## 사용 순서

```powershell
# 1) 최초 설정: 입력창이 뜨면 토큰/앱 시크릿을 입력
powershell -ExecutionPolicy Bypass -File .\setup-instagram-insights.ps1

# 2) 인사이트 수집 (필요할 때마다 재실행 가능)
powershell -ExecutionPolicy Bypass -File .\collect-instagram-insights.ps1
```

`setup-instagram-insights.ps1`을 실행하면:
1. 로컬 GUI 입력창(마스킹 처리)에 토큰과 앱 시크릿을 입력합니다.
2. 값은 현재 Windows 사용자만 복호화 가능한 DPAPI(`CurrentUser` 범위)로 암호화되어
   `%LOCALAPPDATA%\InstagramCodexConnector\config.json`에 저장됩니다.
3. 단기 토큰을 장기 액세스 토큰(약 60일)으로 교환합니다.
4. `graph.instagram.com/me`로 실제 연결 테스트를 수행합니다.
5. `instagram_business_basic`, `instagram_business_manage_insights` 권한 부여 여부를 확인합니다.
6. 만료 10일 전부터 자동 갱신하는 작업 스케줄러 작업(`InstagramCodexConnector-TokenRenew`,
   매일 03:00 실행)을 등록합니다.
7. 매일 오전 10시에 팔로워/콘텐츠 성과 브리프를 자동 생성하는 작업 스케줄러 작업
   (`InstagramCodexConnector-DailyBrief`)을 등록합니다.
8. 콘솔에는 **계정명 / 연결 성공 여부 / 토큰 만료일**만 출력됩니다. 토큰과 시크릿
   원문은 어떤 경우에도 출력되지 않습니다.

이미 예전에 `setup-instagram-insights.ps1`을 실행해 두었다면(토큰 재입력 없이),
`enable-daily-brief.ps1`만 한 번 실행하면 매일 10시 자동 브리프가 추가로 등록됩니다:

```powershell
powershell -ExecutionPolicy Bypass -File .\enable-daily-brief.ps1
```

`collect-instagram-insights.ps1`을 실행하면:
- 저장된 토큰이 10일 이내 만료라면 수집 전에 `renew-instagram-token.ps1`을 먼저 호출해 갱신합니다.
- 프로필 정보와 최근 콘텐츠 5개(기본값, `-MediaCount`로 조정 가능)의 조회수/도달/저장/공유
  지표를 가져옵니다.
- 결과를 `%USERPROFILE%\Documents\InstagramInsights\` 아래에
  `instagram-insights-YYYYMMDD-HHmmss.json` / `.md`와 `latest.json` / `latest.md`로 저장합니다.

`daily-instagram-brief.ps1`을 실행하면(매일 10시 자동 실행 또는 수동 실행):
- 프로필(팔로워 수 포함)과 최근 콘텐츠 5개 지표를 가져와, 직전 실행 대비 **팔로워 증감**과
  **최고 성과 게시물**을 포함한 한 문단 요약을 만듭니다.
- `%USERPROFILE%\Documents\InstagramInsights\brief-YYYY-MM-DD.md`, `latest-brief.md`로 저장합니다.
- 이 저장소 안에서 실행 중이면 `data/instagram.json`을 갱신하고, 변경 사항이 있으면
  **자동으로 `git pull --ff-only` → `git add` → `git commit` → `git push`**를 시도해
  라이브 대시보드에도 자동 반영합니다. 이 자동 push는 Windows의 Git 자격 증명 관리자에
  이미 저장된 인증 정보를 사용하므로, 이전에 같은 저장소로 수동 push를 한 번이라도
  성공한 적이 있다면 별도 설정 없이 동작합니다. push가 실패해도(네트워크/권한 등) 로컬
  브리프 생성 자체는 실패로 처리하지 않고 경고만 출력합니다.
- `dashboard.html`의 "인스타그램" 탭 상단 "오늘의 브리프" 카드와 "팔로워" KPI에 반영됩니다.

## 보안 설계

- 토큰/시크릿은 채팅이나 스크립트 인자로 절대 요구하지 않고, Windows 로컬 GUI 입력창으로만 입력받습니다.
- 저장 시 `System.Security.Cryptography.ProtectedData`(DPAPI, `DataProtectionScope.CurrentUser`)로
  암호화하므로, 같은 PC라도 다른 Windows 계정에서는 복호화할 수 없고 파일을 다른 PC로
  복사해도 복호화되지 않습니다.
- `config.json`은 현재 사용자에게만 `FullControl`을 부여하도록 ACL을 재설정합니다.
- 모든 Graph API 호출 오류 메시지는 `access_token=`, `client_secret=` 값을 로그에 남기기 전에
  마스킹합니다.
- 콘솔 출력, 로그, 결과 JSON/Markdown 어디에도 토큰/시크릿 원문이 기록되지 않습니다.

## 경로 이식성

모든 경로는 `$env:LOCALAPPDATA`, `$env:USERPROFILE`, `$env:USERNAME`, `$PSScriptRoot`
기반으로 계산되므로, 폴더째 다른 Windows PC로 복사해서 그대로 실행할 수 있습니다.
(단, 계정별로 `setup-instagram-insights.ps1`은 각 PC에서 다시 실행해 자격 증명을 입력해야 합니다 —
DPAPI 암호화 값은 사용자/기기에 종속되어 이식되지 않습니다.)

## 자동 갱신 / 자동 브리프 재설정 / 제거

```powershell
# 예약 작업 상태 확인
Get-ScheduledTask -TaskName 'InstagramCodexConnector-TokenRenew'
Get-ScheduledTask -TaskName 'InstagramCodexConnector-DailyBrief'

# 예약 작업 제거
Unregister-ScheduledTask -TaskName 'InstagramCodexConnector-TokenRenew' -Confirm:$false
Unregister-ScheduledTask -TaskName 'InstagramCodexConnector-DailyBrief' -Confirm:$false

# 설정 초기화 (토큰 재입력부터 다시 시작하고 싶을 때)
Remove-Item "$env:LOCALAPPDATA\InstagramCodexConnector" -Recurse -Force
```

## 웹 대시보드(`dashboard.html`) 연동

`collect-instagram-insights.ps1`을 이 저장소 안에서 실행하면(`instagram-insights-connector`
폴더가 리포 루트의 형제 폴더인 경우), `%USERPROFILE%\Documents\InstagramInsights\`뿐 아니라
리포 루트의 `data/instagram.json`도 함께 갱신합니다. 이 파일에는 계정명·게시물 수·조회수·도달·
저장·공유 등 **수치 데이터만** 담기며, 토큰이나 앱 시크릿은 어떤 경우에도 포함되지 않습니다.

`dashboard.html`의 "인스타그램" 탭은 이 `data/instagram.json`을 불러와 표시합니다. 최신 수치를
실제 라이브 대시보드(GitHub Pages)에 반영하려면:

```powershell
git add data/instagram.json
git commit -m "Instagram 인사이트 갱신"
git push
```

`collect-instagram-insights.ps1`/`daily-instagram-brief.ps1`은 기본적으로 최근 게시물을
넉넉히(기본 25개, `-WeeklyMediaCount`로 조정) 함께 가져와 `data/instagram.json`의
`weeklyMedia` 필드에 담습니다(로컬 리포트·"게시물별 성과" 표는 그중 최근 5개만 그대로 사용).
이 표본을 바탕으로 "인스타그램" 탭에서 다음 두 가지를 자동 계산합니다 (별도 API 호출 없이
브라우저에서 계산):

- **이번 주 성과 TOP3**: 종합 점수(`조회수 + 도달 + (저장+공유)×10`) 기준 상위 3개 게시물
- **저장률 높은 콘텐츠 공통점**: 저장률(`저장 ÷ 도달`) 상위 게시물의 콘텐츠 유형·해시태그·게시 요일 패턴을 전체 평균과 비교

이번 주(최근 7일) 게시물이 3개 미만이면 표본 부족을 안내하고 최근 게시물 전체 기준으로
대체 분석합니다.

`daily-instagram-brief.ps1`을 실행하면 아래 3가지도 함께 계산되어 `data/instagram.json`의
`followerHistory`/`surging` 필드에 누적됩니다 (별도 API 호출 없이, 매일 실행 시점의 스냅샷을
비교하는 방식):

- **팔로워 증가 &amp; 콘텐츠 발행 추이 그래프**: 매일 브리프 실행 시점의 팔로워 수를 최근 60일까지
  누적한 `followerHistory`와, 같은 기간 게시물 발행 일자를 겹쳐 막대+선 그래프로 표시합니다.
  최소 2일치 이력이 쌓여야 그래프가 나타나며, 그전에는 안내 문구만 표시됩니다.
- **다음 콘텐츠 주제 추천 3개**: 최근 표본(기본 25개)에서 종합 점수 상위 콘텐츠의 유형·해시태그·
  저장률·게시 요일 패턴을 규칙 기반으로 분석해 추천합니다. AI가 생성한 것이 아니라 통계 기반
  규칙으로 계산되며, 표본이 3개 미만이면 추천 대신 안내 문구를 표시합니다.
- **조회수 급상승 알림**: 오늘 수집한 `weeklyMedia`와 직전 실행(전일)의 값을 게시물 ID로 비교해,
  조회수가 **전일 대비 30% 이상 또는 1,000회 이상** 증가한 게시물을 최대 5건까지 급상승 목록으로
  표시합니다. 게시 빈도가 낮아 비교 대상 게시물이 없으면(신규 게시물 등) 자동으로 건너뜁니다.

### 콘텐츠 성과 분석 (직무별 순위 · 연령/성별 인구통계)

**직무별 인기 순위**는 게시물 캡션의 직무 해시태그로 분류합니다. 앞으로 게시물을 올릴 때
캡션에 아래 해시태그 중 하나를 포함하면 정확하게 분류됩니다 (접두사 없이, `job_pipeline`의
직무 분류 체계와 동일):

| 해시태그 | 카테고리 |
|---|---|
| `#마케팅` | 마케팅 |
| `#MD` | MD |
| `#데이터` | 데이터 |
| `#개발` | 개발 |
| `#기획PM` | 기획/PM |
| `#운영` | 운영 |
| `#미디어` | 미디어 |
| `#사업개발` 또는 `#영업` | 사업개발 |
| `#코치트레이너` | 코치/트레이너 |
| `#대외활동` (또는 `#공모전`/`#서포터즈`/`#인턴`) | 대외활동 |

해시태그가 없는 과거 게시물은 캡션 키워드로 자동 추정합니다 (예: "백엔드 개발자 채용" →
개발). 둘 다 해당하지 않으면 "기타"로 분류되며, 태깅된 게시물이 하나도 없으면 순위 대신
해시태그를 추가해 달라는 안내 문구가 표시됩니다. 정렬 기준(도달/저장/참여율)은 대시보드에서
드롭다운으로 바로 전환할 수 있습니다.

**연령대별/성별 선호도**는 `engaged_audience_demographics` API(최근 30일, `-Timeframe`으로
조정 가능)로 가져오는 **최근 실제로 반응(좋아요·댓글·저장 등)한 참여자의 연령×성별 분포**입니다.
단순히 팔로우만 하는 사람 전체(`follower_demographics`)보다 "실제로 반응하는 사람" 기준이라
더 의미 있는 신호지만, 이 지표 역시 Instagram API의 한계로 특정 게시물 하나와 연결되지는
않고 최근 30일 전체 참여자의 집계입니다 — "이 게시물에 어떤 연령/성별이 반응했는지" 같은
게시물 단위 교차분석은 Instagram API로 제공되지 않습니다. `daily-instagram-brief.ps1`이 매일
실행 시 이 지표를 함께 가져와 `data/instagram.json`의 `engagedDemographics` 필드에
저장합니다. 참여자 수가 Meta의 최소 요건에 못 미치는 등 조회에 실패하면(치명적 오류로
처리하지 않고) 이전 값을 유지하며, 데이터가 아예 없으면 대시보드에 "데이터 연동 준비 중"
빈 상태가 표시됩니다.

게시물 단위로 정확한 연령/성별 데이터가 꼭 필요하다면, 해당 게시물을 Meta 광고관리자로
유료 홍보(부스트)했을 때만 Marketing API의 광고 인사이트에서 얻을 수 있습니다 — 이건
별도의 광고 계정 연동이 필요한 완전히 다른 작업입니다.

### 성과 추이 히스토리

`daily-instagram-brief.ps1`이 매일 실행될 때마다 그날의 핵심 지표를 한 건씩
`data/instagram.json`의 `analysisHistory` 필드(최근 60일 누적)에 남깁니다:

- `followers`, `viewsAvg`(평균 조회수), `reachSum`(도달 합계), `engagementSum`(저장+공유 합계)
- `topCategory`: 그날 표본에서 도달 합계가 가장 큰 직무 카테고리 (`Get-InstagramJobCategory`로
  분류 — dashboard.html의 `igJobCategoryOf()`와 동일한 규칙을 PowerShell로 옮긴 것이며,
  분류 규칙을 바꿀 때는 두 파일을 함께 수정해야 합니다)
- `surgingCount`: 그날 감지된 급상승 콘텐츠 건수

대시보드의 "📅 성과 추이 히스토리" 섹션이 이 값들을 일별 추이 그래프와
"최근 N일간 가장 자주 1위였던 직무" 같은 요약 인사이트로 보여줍니다. 최소 2일치가
쌓여야 그래프가 나타나며, 그 전에는 안내 문구만 표시됩니다.

커밋을 main 브랜치에 푸시하면 `deploy.yml`이 자동으로 사이트를 다시 빌드해 배포합니다. 이 파일을
커밋하지 않으면 대시보드는 예시(Mock) 데이터를 계속 표시합니다.

## 문제 해결

- **`instagram_business_basic` / `instagram_business_manage_insights` 누락**: Meta 개발자
  콘솔에서 앱의 Instagram 사용 사례(Use case)에 해당 권한이 추가되어 있고, 로그인 시 해당
  스코프로 동의했는지 확인하세요.
- **일부 콘텐츠의 지표가 `null`**: 미디어 유형(이미지/릴스/캐러셀)에 따라 지원되는 지표가
  달라 API가 일부 지표를 거부할 수 있습니다. 스크립트는 자동으로 지표별 개별 재시도를
  수행하며, 그래도 실패한 지표만 `null`로 남습니다.
- **DPAPI 오류**: PowerShell 7을 쓴다면 Windows용으로 실행 중인지 확인하세요 (macOS/Linux의
  PowerShell 7에서는 DPAPI가 지원되지 않습니다).
