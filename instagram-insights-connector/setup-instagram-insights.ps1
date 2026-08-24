<#
.SYNOPSIS
    Instagram Insights Windows Connector - 초기 설정 (재사용 가능).
.DESCRIPTION
    1) 로컬 GUI 입력창으로 Instagram 액세스 토큰 / 앱 시크릿을 입력받고
    2) 현재 Windows 사용자만 복호화할 수 있도록 DPAPI로 암호화하여
       %LOCALAPPDATA%\InstagramCodexConnector\config.json 에 저장하고
    3) 장기 액세스 토큰으로 교환한 뒤
    4) graph.instagram.com 으로 실제 연결 테스트를 수행하고
    5) instagram_business_basic / instagram_business_manage_insights 권한을 확인하고
    6) 만료 10일 전 자동 갱신을 위한 작업 스케줄러 작업을 등록합니다.

    토큰과 앱 시크릿 값은 어떤 경우에도 콘솔/로그/파일에 평문으로 출력되지 않습니다.
    출력되는 것은 계정명, 연결 성공 여부, 토큰 만료일뿐입니다.
.NOTES
    고정된 사용자명이나 경로 대신 $env:LOCALAPPDATA / $env:USERPROFILE 을 사용하므로
    다른 Windows PC에서도 그대로 동작합니다.
#>

[CmdletBinding()]
param()

. "$PSScriptRoot\InstagramConnector.Common.ps1"

Write-Host '=== Instagram Insights Connector 설정 시작 ===' -ForegroundColor Cyan

$creds = Show-CredentialInputForm
if (-not $creds) {
    Write-Host '입력이 취소되었거나 값이 비어 있어 설정을 종료합니다.' -ForegroundColor Yellow
    exit 1
}

$igProfile = $null
$expiresAt = $null
$granted = @()
$missing = @()
$taskRegistered = $false

try {
    Write-Host '장기 액세스 토큰으로 교환 중...' -ForegroundColor Cyan
    $exchange = Get-InstagramLongLivedToken -InputToken $creds.AccessToken -AppSecret $creds.AppSecret
    $longLivedToken = $exchange.access_token
    $expiresAt = New-ExpiryTimestamp -ExpiresInSeconds $exchange.expires_in

    Write-Host '연결 테스트 중 (graph.instagram.com)...' -ForegroundColor Cyan
    $igProfile = Get-InstagramProfile -AccessToken $longLivedToken

    Write-Host '권한 확인 중...' -ForegroundColor Cyan
    $granted = Get-InstagramGrantedPermissions -AccessToken $longLivedToken
    $missing = @($script:RequiredScopes | Where-Object { $granted -notcontains $_ })

    $config = @{
        encryptedAccessToken = Protect-PlainText -PlainText $longLivedToken
        encryptedAppSecret   = Protect-PlainText -PlainText $creds.AppSecret
        igUserId             = $igProfile.id
        username             = $igProfile.username
        tokenType            = 'long_lived'
        expiresAt            = $expiresAt
        lastRefreshed        = (Get-Date).ToUniversalTime().ToString('o')
        grantedPermissions   = $granted
    }
    Save-InstagramConfig -Config $config

    $renewScript = Join-Path $PSScriptRoot 'renew-instagram-token.ps1'
    $taskRegistered = Register-InstagramTokenRenewalTask -RenewScriptPath $renewScript
}
catch {
    Write-Host ''
    Write-Host '연결 실패' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
finally {
    # 평문 자격 증명을 담고 있던 변수를 최대한 빨리 비웁니다.
    $creds = $null
    $longLivedToken = $null
    [System.GC]::Collect()
}

Write-Host ''
Write-Host '=== 연결 결과 ===' -ForegroundColor Green
Write-Host ("계정명        : {0}" -f $igProfile.username)
Write-Host ("연결 성공 여부 : {0}" -f 'YES')
Write-Host ("토큰 만료일    : {0}" -f ([datetime]::Parse($expiresAt).ToLocalTime().ToString('yyyy-MM-dd HH:mm')))

if ($missing.Count -gt 0) {
    Write-Host ("누락된 필수 권한: {0}" -f ($missing -join ', ')) -ForegroundColor Yellow
} else {
    Write-Host '필수 권한 확인 : instagram_business_basic, instagram_business_manage_insights 모두 부여됨' -ForegroundColor Green
}

if ($taskRegistered) {
    Write-Host '자동 갱신 예약 작업(InstagramCodexConnector-TokenRenew)이 등록되었습니다. (만료 10일 전 자동 갱신)' -ForegroundColor Green
} else {
    Write-Host '자동 갱신 예약 작업 등록에 실패했습니다. renew-instagram-token.ps1을 수동으로 예약해 주세요.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host ("설정 파일 위치: {0}" -f (Get-InstagramConfigPath))
