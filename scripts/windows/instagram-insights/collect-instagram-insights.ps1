<#
    collect-instagram-insights.ps1

    Reusable script: fetches your Instagram profile plus views / reach /
    saved / shares for your last 5 posts, using the token saved by
    setup-instagram-insights.ps1, and writes a JSON + Markdown report.

    Usage:
        powershell -ExecutionPolicy Bypass -File .\collect-instagram-insights.ps1
#>

[CmdletBinding()]
param(
    [int]$MediaLimit = 5
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$ConnectorDir = Join-Path $env:LOCALAPPDATA 'InstagramCodexConnector'
$ConfigPath   = Join-Path $ConnectorDir 'config.json'
$ReportsDir   = Join-Path $ConnectorDir 'reports'
$LogPath      = Join-Path $ConnectorDir 'connector.log'
$RenewScript  = Join-Path $PSScriptRoot 'renew-instagram-token.ps1'

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path $LogPath -Value $line
}

function Unprotect-Secret {
    param([Parameter(Mandatory)][pscustomobject]$Secret)
    Add-Type -AssemblyName System.Security
    $cipherBytes  = [Convert]::FromBase64String($Secret.cipher)
    $entropyBytes = [Convert]::FromBase64String($Secret.entropy)
    $plainBytes = [System.Security.Cryptography.ProtectedData]::Unprotect(
        $cipherBytes, $entropyBytes, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
    [System.Text.Encoding]::UTF8.GetString($plainBytes)
}

if (-not (Test-Path $ConfigPath)) {
    throw "설정 파일이 없습니다: $ConfigPath  (먼저 setup-instagram-insights.ps1 을 실행하세요.)"
}

New-Item -ItemType Directory -Path $ReportsDir -Force | Out-Null

$config = Get-Content -Path $ConfigPath -Raw | ConvertFrom-Json

# Renew first if we're within the 10-day window, so this collection uses a fresh token.
$expiresAtUtc = [datetime]::Parse($config.expiresAtUtc, $null, [System.Globalization.DateTimeStyles]::RoundtripKind)
if ((($expiresAtUtc - (Get-Date).ToUniversalTime()).TotalDays -le 10) -and (Test-Path $RenewScript)) {
    Write-Log 'collect: token close to expiry, invoking renew script first.'
    & $RenewScript | Out-Null
    $config = Get-Content -Path $ConfigPath -Raw | ConvertFrom-Json
}

$accessToken = Unprotect-Secret -Secret $config.accessToken

try {
    # --- Profile -----------------------------------------------------
    $meUri = 'https://graph.instagram.com/me' +
        '?fields=id,username,account_type,media_count' +
        '&access_token=' + [uri]::EscapeDataString($accessToken)
    $igProfile = Invoke-RestMethod -Method Get -Uri $meUri

    # --- Last N media --------------------------------------------------
    $mediaUri = 'https://graph.instagram.com/me/media' +
        '?fields=id,caption,media_type,media_product_type,timestamp,permalink' +
        '&limit=' + $MediaLimit +
        '&access_token=' + [uri]::EscapeDataString($accessToken)
    $mediaResponse = Invoke-RestMethod -Method Get -Uri $mediaUri
    $mediaItems = @($mediaResponse.data)

    $metricNames = @('views', 'reach', 'saved', 'shares')
    $results = foreach ($item in $mediaItems) {
        $metrics = [ordered]@{ views = $null; reach = $null; saved = $null; shares = $null }
        try {
            $insightsUri = 'https://graph.instagram.com/{0}/insights?metric={1}&access_token={2}' -f `
                $item.id, ($metricNames -join ','), [uri]::EscapeDataString($accessToken)
            $insightsResponse = Invoke-RestMethod -Method Get -Uri $insightsUri
            foreach ($m in $insightsResponse.data) {
                $value = $null
                if ($m.PSObject.Properties.Name -contains 'values' -and $m.values) {
                    $value = $m.values[0].value
                } elseif ($m.PSObject.Properties.Name -contains 'total_value') {
                    $value = $m.total_value.value
                }
                $metrics[$m.name] = $value
            }
        } catch {
            Write-Log ("collect: insights fetch failed for media {0}: {1}" -f $item.id, $_.Exception.Message)
        }

        [ordered]@{
            id               = $item.id
            caption          = if ($item.caption) { $item.caption } else { '' }
            mediaType        = $item.media_type
            mediaProductType = $item.media_product_type
            timestamp        = $item.timestamp
            permalink        = $item.permalink
            views            = $metrics.views
            reach            = $metrics.reach
            saved            = $metrics.saved
            shares           = $metrics.shares
        }
    }

    $report = [ordered]@{
        generatedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
        profile = [ordered]@{
            username    = $igProfile.username
            userId      = $igProfile.id
            accountType = $igProfile.account_type
            mediaCount  = $igProfile.media_count
        }
        media = $results
    }

    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $jsonPath = Join-Path $ReportsDir "insights-$timestamp.json"
    $mdPath   = Join-Path $ReportsDir "insights-$timestamp.md"

    $report | ConvertTo-Json -Depth 8 | Set-Content -Path $jsonPath -Encoding UTF8

    $md = New-Object System.Text.StringBuilder
    [void]$md.AppendLine("# Instagram Insights — $($igProfile.username)")
    [void]$md.AppendLine('')
    [void]$md.AppendLine("- 생성 시각(UTC): $($report.generatedAtUtc)")
    [void]$md.AppendLine("- 계정 유형: $($igProfile.account_type)")
    [void]$md.AppendLine("- 총 게시물 수: $($igProfile.media_count)")
    [void]$md.AppendLine('')
    [void]$md.AppendLine('| 게시일 | 유형 | 조회(views) | 도달(reach) | 저장(saved) | 공유(shares) | 링크 |')
    [void]$md.AppendLine('|---|---|---|---|---|---|---|')
    foreach ($r in $results) {
        $shortCaption = if ($r.caption.Length -gt 0) { ($r.caption -replace '[\r\n]+', ' ') } else { '' }
        [void]$md.AppendLine("| $($r.timestamp) | $($r.mediaProductType) | $($r.views) | $($r.reach) | $($r.saved) | $($r.shares) | [link]($($r.permalink)) |")
    }
    Set-Content -Path $mdPath -Value $md.ToString() -Encoding UTF8

    Write-Log "collect: report written to $jsonPath and $mdPath"

    Write-Host ''
    Write-Host '=== Instagram Insights 수집 완료 ===' -ForegroundColor Green
    Write-Host ("계정명: {0}" -f $igProfile.username)
    Write-Host ("수집된 게시물 수: {0}" -f $results.Count)
    Write-Host ("JSON 저장 위치: {0}" -f $jsonPath)
    Write-Host ("Markdown 저장 위치: {0}" -f $mdPath)
    Write-Host ''
}
finally {
    Remove-Variable accessToken -ErrorAction SilentlyContinue
    [System.GC]::Collect()
}
