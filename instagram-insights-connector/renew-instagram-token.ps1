<#
.SYNOPSIS
    Instagram 장기 액세스 토큰 자동 갱신.
.DESCRIPTION
    저장된 토큰 만료일까지 남은 일수가 -RenewThresholdDays(기본 10일) 이하일 때만
    실제로 갱신을 수행합니다. 작업 스케줄러(InstagramCodexConnector-TokenRenew)가
    매일 이 스크립트를 호출하므로, 매일 실행되어도 만료 임박 전에는 아무 일도 하지 않습니다.
    setup-instagram-insights.ps1으로 이미 설정이 되어 있어야 합니다.
    토큰 값은 콘솔/로그에 출력되지 않습니다.
#>

[CmdletBinding()]
param(
    [int]$RenewThresholdDays = 10
)

. (Join-Path $PSScriptRoot 'InstagramConnector.Common.ps1')

$config = Get-InstagramConfig
if (-not $config) {
    Write-Warning '설정 파일을 찾을 수 없습니다. setup-instagram-insights.ps1을 먼저 실행하세요.'
    exit 1
}

$daysLeft = Get-DaysUntilExpiry -ExpiresAtIso $config.expiresAt
if ($daysLeft -gt $RenewThresholdDays) {
    Write-Host ("토큰 만료까지 {0:N1}일 남음 - 갱신 불필요" -f $daysLeft)
    exit 0
}

$token = $null
try {
    $token = Get-DecryptedAccessToken -Config $config
    $refresh = Invoke-InstagramTokenRefresh -LongLivedToken $token
    $newExpiresAt = New-ExpiryTimestamp -ExpiresInSeconds $refresh.expires_in

    $updated = @{
        encryptedAccessToken = Protect-PlainText -PlainText $refresh.access_token
        encryptedAppSecret   = $config.encryptedAppSecret
        igUserId             = $config.igUserId
        username             = $config.username
        tokenType            = 'long_lived'
        expiresAt            = $newExpiresAt
        lastRefreshed        = (Get-Date).ToUniversalTime().ToString('o')
        grantedPermissions   = $config.grantedPermissions
    }
    Save-InstagramConfig -Config $updated

    Write-Host ("토큰이 갱신되었습니다. 새 만료일: {0}" -f ([datetime]::Parse($newExpiresAt).ToLocalTime().ToString('yyyy-MM-dd HH:mm')))
}
catch {
    Write-Warning "토큰 갱신 실패: $($_.Exception.Message)"
    exit 1
}
finally {
    $token = $null
    [System.GC]::Collect()
}
