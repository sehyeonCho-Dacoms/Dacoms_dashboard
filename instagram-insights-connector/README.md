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
7. 콘솔에는 **계정명 / 연결 성공 여부 / 토큰 만료일**만 출력됩니다. 토큰과 시크릿
   원문은 어떤 경우에도 출력되지 않습니다.

`collect-instagram-insights.ps1`을 실행하면:
- 저장된 토큰이 10일 이내 만료라면 수집 전에 `renew-instagram-token.ps1`을 먼저 호출해 갱신합니다.
- 프로필 정보와 최근 콘텐츠 5개(기본값, `-MediaCount`로 조정 가능)의 조회수/도달/저장/공유
  지표를 가져옵니다.
- 결과를 `%USERPROFILE%\Documents\InstagramInsights\` 아래에
  `instagram-insights-YYYYMMDD-HHmmss.json` / `.md`와 `latest.json` / `latest.md`로 저장합니다.

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

## 자동 갱신 재설정 / 제거

```powershell
# 예약 작업 상태 확인
Get-ScheduledTask -TaskName 'InstagramCodexConnector-TokenRenew'

# 예약 작업 제거
Unregister-ScheduledTask -TaskName 'InstagramCodexConnector-TokenRenew' -Confirm:$false

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
