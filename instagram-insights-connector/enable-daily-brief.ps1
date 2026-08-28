<#
.SYNOPSIS
    매일 오전 10시 자동 브리프(daily-instagram-brief.ps1) 예약 작업을 등록합니다.
.DESCRIPTION
    이미 setup-instagram-insights.ps1로 설정을 마친 경우, 토큰을 다시 입력할 필요 없이
    이 스크립트만 한 번 실행하면 매일 10:00에 daily-instagram-brief.ps1이 자동으로
    실행되도록 작업 스케줄러에 등록됩니다.
#>

[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot 'InstagramConnector.Common.ps1')

if (-not (Get-InstagramConfig)) {
    Write-Error '설정 파일을 찾을 수 없습니다. 먼저 setup-instagram-insights.ps1을 실행하세요.'
    exit 1
}

$briefScript = Join-Path $PSScriptRoot 'daily-instagram-brief.ps1'
if (Register-InstagramDailyBriefTask -BriefScriptPath $briefScript) {
    Write-Host '매일 오전 10시 자동 브리프(InstagramCodexConnector-DailyBrief)가 등록되었습니다.' -ForegroundColor Green
    Write-Host '지금 바로 한 번 실행해 보려면: .\daily-instagram-brief.ps1' -ForegroundColor Cyan
} else {
    Write-Host '예약 작업 등록에 실패했습니다. 위 경고 메시지를 확인하세요.' -ForegroundColor Yellow
    exit 1
}
