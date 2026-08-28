<#
.SYNOPSIS
    GitHub Actions(리눅스)에서 인스타그램 커넥터를 돌리기 위한 자격증명 어댑터.

.DESCRIPTION
    기존 커넥터는 Windows DPAPI로 토큰을 암호화해 로컬 파일에 저장합니다.
    DPAPI는 사용자+PC에 묶여 있어 CI로 그대로 옮길 수 없습니다.

    다만 Windows 의존성은 아래 3곳뿐이고, Graph API 호출·인사이트 집계·
    브리핑 생성 로직은 전부 플랫폼 중립입니다. 그래서 재작성 대신
    "자격증명을 읽는 함수"만 환경변수 버전으로 갈아끼웁니다.

      1) Assert-WindowsPlatform   → CI에서는 건너뜀 (Common.ps1 에서 게이트)
      2) Get-InstagramConfig      → 환경변수로 구성
      3) Get-Decrypted*           → 환경변수 평문 반환

    Windows 작업 스케줄러 등록 함수(Register-*)는 CI에서 호출되지 않으므로
    건드리지 않습니다.

.NOTES
    반드시 InstagramConnector.Common.ps1 을 dot-source 한 "뒤에" 로드해야
    원본 함수를 덮어씁니다.

    필요한 환경변수 (GitHub Secrets):
      IG_ACCESS_TOKEN   장기 액세스 토큰 (필수)
      IG_USER_ID        인스타그램 사용자 ID (선택, me 로 대체 가능)
      IG_APP_SECRET     앱 시크릿 (토큰 갱신 시에만 필요)
      IG_TOKEN_EXPIRES_AT  ISO8601 만료시각 (선택)
#>

Set-StrictMode -Version Latest

if (-not $env:IG_ACCESS_TOKEN) {
    throw 'CI.Bootstrap: 환경변수 IG_ACCESS_TOKEN 이 없습니다. GitHub Secrets 를 확인하세요.'
}

# ── 1. 플랫폼 검사 무력화 (Common.ps1 이 이미 게이트하지만 이중 안전장치) ──
function Assert-WindowsPlatform { }

# ── 2. 설정 객체를 환경변수로 구성 ──────────────────────────────
function Get-InstagramConfig {
    return [pscustomobject]@{
        userId                = $env:IG_USER_ID
        encryptedAccessToken  = '(env)'    # 실제로 쓰이지 않음
        encryptedAppSecret    = '(env)'
        expiresAt             = $env:IG_TOKEN_EXPIRES_AT
        source                = 'ci-env'
    }
}

# ── 3. 복호화 대신 환경변수 평문 반환 ───────────────────────────
function Get-DecryptedAccessToken {
    param($Config)
    return $env:IG_ACCESS_TOKEN
}

function Get-DecryptedAppSecret {
    param($Config)
    return $env:IG_APP_SECRET
}

# ── 4. 자동 갱신 방지 ───────────────────────────────────────────
# 수집 스크립트는 만료 10일 이내면 renew 스크립트를 자동 호출합니다.
# CI에서는 갱신된 토큰을 Secret 에 다시 쓸 수 없으므로(별도 워크플로가 담당),
# 수집 중 갱신이 일어나지 않도록 충분히 큰 값을 반환합니다.
# 실제 만료일은 IG_TOKEN_EXPIRES_AT 이 있으면 그대로 계산해 경고만 남깁니다.
function Get-DaysUntilExpiry {
    param([string]$ExpiresAtIso)

    $iso = if ($ExpiresAtIso) { $ExpiresAtIso } else { $env:IG_TOKEN_EXPIRES_AT }
    if ($iso) {
        try {
            $left = [int]([datetime]::Parse($iso).ToUniversalTime() - [datetime]::UtcNow).TotalDays
            if ($left -le 14) {
                Write-Host "::warning::인스타그램 토큰 만료까지 $left 일 남았습니다. 갱신 워크플로를 확인하세요."
            }
            Write-Host "[CI] 토큰 잔여일: $left 일 (수집 중 자동갱신은 비활성)"
        } catch {
            Write-Host '[CI] IG_TOKEN_EXPIRES_AT 파싱 실패 — 만료 검사 건너뜀'
        }
    }
    return 9999   # 수집 스크립트가 renew 를 호출하지 않도록
}

# ── 5. 진단 출력 (시크릿은 절대 출력하지 않음) ──────────────────
Write-Host '[CI] CI.Bootstrap 로드됨 — 자격증명을 환경변수에서 읽습니다.'
Write-Host ("[CI] IG_ACCESS_TOKEN 길이: {0}" -f $env:IG_ACCESS_TOKEN.Length)
Write-Host ("[CI] IG_USER_ID 설정됨: {0}" -f [bool]$env:IG_USER_ID)
Write-Host ("[CI] IG_APP_SECRET 설정됨: {0}" -f [bool]$env:IG_APP_SECRET)
