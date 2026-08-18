<#
.SYNOPSIS
    프로필 및 최근 콘텐츠 5개의 조회/도달/저장/공유 지표를 수집합니다.
.DESCRIPTION
    setup-instagram-insights.ps1으로 저장된 암호화된 토큰을 사용해
    graph.instagram.com에서 프로필과 최근 미디어 인사이트를 가져오고,
    결과를 JSON과 Markdown 파일로 저장합니다.
    토큰이 10일 이내에 만료되면 수집 전에 자동으로 먼저 갱신합니다.
    토큰/시크릿 값은 콘솔/로그/결과 파일 어디에도 출력되지 않습니다.
#>

[CmdletBinding()]
param(
    [int]$MediaCount = 5,
    [string]$OutputDir = (Join-Path $env:USERPROFILE 'Documents\InstagramInsights')
)

. "$PSScriptRoot\InstagramConnector.Common.ps1"

$config = Get-InstagramConfig
if (-not $config) {
    Write-Error '설정 파일을 찾을 수 없습니다. 먼저 setup-instagram-insights.ps1을 실행하세요.'
    exit 1
}

$daysLeft = Get-DaysUntilExpiry -ExpiresAtIso $config.expiresAt
if ($daysLeft -le 10) {
    Write-Host '토큰 만료가 임박하여 수집 전에 먼저 갱신합니다...' -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot 'renew-instagram-token.ps1') | Out-Null
    $config = Get-InstagramConfig
}

$token = $null
try {
    $token = Get-DecryptedAccessToken -Config $config

    Write-Host '프로필 정보 가져오는 중...' -ForegroundColor Cyan
    $igProfile = Get-InstagramProfile -AccessToken $token

    Write-Host ("최근 콘텐츠 {0}개 가져오는 중..." -f $MediaCount) -ForegroundColor Cyan
    $mediaList = @(Get-RecentMedia -AccessToken $token -Limit $MediaCount)

    $mediaResults = @()
    foreach ($media in $mediaList) {
        Write-Host ("  - {0} 지표 조회 중" -f $media.id)
        $insights = Get-MediaInsights -MediaId $media.id -AccessToken $token
        $mediaResults += [ordered]@{
            id               = $media.id
            caption          = $media.caption
            mediaType        = $media.media_type
            mediaProductType = $media.media_product_type
            permalink        = $media.permalink
            timestamp        = $media.timestamp
            views            = $insights.views
            reach            = $insights.reach
            saved            = $insights.saved
            shares           = $insights.shares
        }
    }

    $report = [ordered]@{
        generatedAt = (Get-Date).ToUniversalTime().ToString('o')
        account     = [ordered]@{
            username    = $igProfile.username
            id          = $igProfile.id
            accountType = $igProfile.account_type
            mediaCount  = $igProfile.media_count
        }
        media = $mediaResults
    }

    if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null }

    $stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
    $jsonPath   = Join-Path $OutputDir "instagram-insights-$stamp.json"
    $mdPath     = Join-Path $OutputDir "instagram-insights-$stamp.md"
    $jsonLatest = Join-Path $OutputDir 'latest.json'
    $mdLatest   = Join-Path $OutputDir 'latest.md'

    $report | ConvertTo-Json -Depth 6 | Set-Content -Path $jsonPath -Encoding UTF8
    Copy-Item -Path $jsonPath -Destination $jsonLatest -Force

    $md = New-Object System.Text.StringBuilder
    [void]$md.AppendLine("# Instagram Insights - $($igProfile.username)")
    [void]$md.AppendLine()
    [void]$md.AppendLine("생성 시각: $((Get-Date).ToString('yyyy-MM-dd HH:mm'))")
    [void]$md.AppendLine("계정 유형: $($igProfile.account_type)  |  총 게시물: $($igProfile.media_count)")
    [void]$md.AppendLine()
    [void]$md.AppendLine('| 게시일 | 유형 | 조회수 | 도달 | 저장 | 공유 | 링크 |')
    [void]$md.AppendLine('|---|---|---|---|---|---|---|')
    foreach ($m in $mediaResults) {
        $ts = $m.timestamp
        try { $ts = [datetime]::Parse($m.timestamp).ToString('yyyy-MM-dd') } catch { }
        [void]$md.AppendLine("| $ts | $($m.mediaType) | $($m.views) | $($m.reach) | $($m.saved) | $($m.shares) | [열기]($($m.permalink)) |")
    }
    Set-Content -Path $mdPath -Value $md.ToString() -Encoding UTF8
    Copy-Item -Path $mdPath -Destination $mdLatest -Force

    Write-Host ''
    Write-Host '=== 수집 완료 ===' -ForegroundColor Green
    Write-Host ("계정명    : {0}" -f $igProfile.username)
    Write-Host ("콘텐츠 수 : {0}" -f $mediaResults.Count)
    Write-Host ("저장 위치 : {0}" -f $OutputDir)
    Write-Host ("JSON      : {0}" -f $jsonPath)
    Write-Host ("Markdown  : {0}" -f $mdPath)
}
catch {
    Write-Host '데이터 수집 실패' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
finally {
    $token = $null
    [System.GC]::Collect()
}
