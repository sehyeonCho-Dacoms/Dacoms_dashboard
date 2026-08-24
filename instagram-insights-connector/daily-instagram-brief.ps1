<#
.SYNOPSIS
    매일 오전 10시, 팔로워 수와 최근 콘텐츠 5개 성과를 요약한 브리프를 생성합니다.
.DESCRIPTION
    setup-instagram-insights.ps1으로 저장된 암호화된 토큰을 사용해
    graph.instagram.com에서 프로필(팔로워 수 포함)과 최근 콘텐츠 인사이트를 가져와
    사람이 읽기 쉬운 Markdown 브리프를 만듭니다.

    - 로컬 브리프: %USERPROFILE%\Documents\InstagramInsights\brief-YYYY-MM-DD.md, latest-brief.md
    - 대시보드용 데이터: 이 저장소 안에서 실행 중이면 data/instagram.json에 계정 정보·최근 게시물·
      브리프 요약을 갱신하고, 변경 사항이 있으면 자동으로 git add/commit/push하여
      라이브 대시보드(GitHub Pages)에도 반영합니다 (push 실패는 치명적 오류로 처리하지 않습니다).

    토큰이 10일 이내에 만료되면 실행 전에 자동으로 먼저 갱신합니다.
    토큰/시크릿 값은 콘솔/로그/결과 파일 어디에도 출력되지 않습니다.

    이 스크립트는 작업 스케줄러(InstagramCodexConnector-DailyBrief, 매일 10:00)가
    자동으로 실행하도록 설계되어 있어 사용자 상호작용이 필요 없습니다.
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
    Write-Host '토큰 만료가 임박하여 브리프 생성 전에 먼저 갱신합니다...' -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot 'renew-instagram-token.ps1') | Out-Null
    $config = Get-InstagramConfig
}

$token = $null
try {
    $token = Get-DecryptedAccessToken -Config $config

    Write-Host '프로필 및 최근 콘텐츠 정보 가져오는 중...' -ForegroundColor Cyan
    $snapshot = Get-InstagramInsightsSnapshot -AccessToken $token -MediaCount $MediaCount
    $igProfile = $snapshot.Profile
    $mediaResults = $snapshot.Media

    $today = (Get-Date).ToString('yyyy-MM-dd')
    $followers = 0
    if ($null -ne $igProfile.followers_count) { $followers = [int]$igProfile.followers_count }

    $prevState = Get-InstagramBriefState
    $followersDelta = $null
    if ($prevState -and $null -ne $prevState.followers) {
        $followersDelta = $followers - [int]$prevState.followers
    }
    $deltaText =
        if ($null -eq $followersDelta) { '비교 데이터 없음 (첫 브리프)' }
        elseif ($followersDelta -gt 0) { "▲ 전일 대비 $followersDelta 명 증가" }
        elseif ($followersDelta -lt 0) { "▼ 전일 대비 $([math]::Abs($followersDelta)) 명 감소" }
        else { '전일과 동일' }

    $numOrZero = { param($v) if ($null -ne $v) { [int]$v } else { 0 } }
    $viewsSum  = ($mediaResults | ForEach-Object { & $numOrZero $_.views } | Measure-Object -Sum).Sum
    $reachSum  = ($mediaResults | ForEach-Object { & $numOrZero $_.reach } | Measure-Object -Sum).Sum
    $savedSum  = ($mediaResults | ForEach-Object { & $numOrZero $_.saved } | Measure-Object -Sum).Sum
    $sharesSum = ($mediaResults | ForEach-Object { & $numOrZero $_.shares } | Measure-Object -Sum).Sum
    $mediaCount = $mediaResults.Count
    $viewsAvg = if ($mediaCount -gt 0) { [math]::Round($viewsSum / $mediaCount) } else { 0 }

    $topPost = $mediaResults | Sort-Object { & $numOrZero $_.views } -Descending | Select-Object -First 1
    $topCaption = ''
    if ($topPost -and $topPost.caption) { $topCaption = ($topPost.caption -replace '\s+', ' ').Trim() }
    if ($topCaption.Length -gt 40) { $topCaption = $topCaption.Substring(0, 40) + '…' }

    $summary =
        if ($topPost) {
            "팔로워 {0}명 ({1}). 최근 {2}개 게시물 평균 조회수 {3}회, 도달 합계 {4}회, 저장+공유 합계 {5}회. 최고 성과: '{6}' (조회수 {7}회)" -f `
                $followers, $deltaText, $mediaCount, $viewsAvg, $reachSum, ($savedSum + $sharesSum), $topCaption, (& $numOrZero $topPost.views)
        } else {
            "팔로워 {0}명 ({1}). 최근 콘텐츠가 없습니다." -f $followers, $deltaText
        }

    $brief = [ordered]@{
        date           = $today
        followers      = $followers
        followersDelta = $followersDelta
        summary        = $summary
        topPost        = if ($topPost) { [ordered]@{ caption = $topCaption; views = (& $numOrZero $topPost.views); permalink = $topPost.permalink } } else { $null }
    }

    $report = [ordered]@{
        generatedAt = (Get-Date).ToUniversalTime().ToString('o')
        account     = [ordered]@{
            username       = $igProfile.username
            id             = $igProfile.id
            accountType    = $igProfile.account_type
            mediaCount     = $igProfile.media_count
            followersCount = $followers
        }
        media = $mediaResults
        brief = $brief
    }

    if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null }
    $briefMdPath = Join-Path $OutputDir "brief-$today.md"
    $briefMdLatest = Join-Path $OutputDir 'latest-brief.md'

    $md = New-Object System.Text.StringBuilder
    [void]$md.AppendLine("# Instagram 일일 브리프 - $($igProfile.username) ($today)")
    [void]$md.AppendLine()
    [void]$md.AppendLine('## 팔로워')
    [void]$md.AppendLine("- 현재: ${followers}명")
    [void]$md.AppendLine("- 증감: $deltaText")
    [void]$md.AppendLine()
    [void]$md.AppendLine("## 최근 ${mediaCount}개 게시물 성과")
    [void]$md.AppendLine("- 평균 조회수: $viewsAvg 회")
    [void]$md.AppendLine("- 도달 합계: $reachSum 회")
    [void]$md.AppendLine("- 저장 합계: $savedSum 회")
    [void]$md.AppendLine("- 공유 합계: $sharesSum 회")
    [void]$md.AppendLine()
    if ($topPost) {
        [void]$md.AppendLine('## 최고 성과 게시물')
        [void]$md.AppendLine("- $topCaption (조회수 $(& $numOrZero $topPost.views)회)")
        [void]$md.AppendLine("  $($topPost.permalink)")
        [void]$md.AppendLine()
    }
    [void]$md.AppendLine('| 게시일 | 유형 | 조회수 | 도달 | 저장 | 공유 | 링크 |')
    [void]$md.AppendLine('|---|---|---|---|---|---|---|')
    foreach ($m in $mediaResults) {
        $ts = $m.timestamp
        try { $ts = [datetime]::Parse($m.timestamp).ToString('yyyy-MM-dd') } catch { }
        [void]$md.AppendLine("| $ts | $($m.mediaType) | $($m.views) | $($m.reach) | $($m.saved) | $($m.shares) | [열기]($($m.permalink)) |")
    }
    Set-Content -Path $briefMdPath -Value $md.ToString() -Encoding UTF8
    Copy-Item -Path $briefMdPath -Destination $briefMdLatest -Force

    # 대시보드용 데이터 갱신 + (가능하면) 자동 git 반영.
    # 이 저장소 클론 안에서 실행 중일 때만 동작하며, 토큰/시크릿은 절대 포함되지 않습니다.
    $pushed = $false
    $repoRoot = $null
    $repoDataDir = Join-Path $PSScriptRoot '..\data'
    if (Test-Path $repoDataDir) {
        $repoInstagramJson = Join-Path $repoDataDir 'instagram.json'
        $report | ConvertTo-Json -Depth 6 | Set-Content -Path $repoInstagramJson -Encoding UTF8

        $candidateRoot = Join-Path $PSScriptRoot '..'
        if (Test-Path (Join-Path $candidateRoot '.git')) {
            $repoRoot = (Resolve-Path $candidateRoot).Path
            try {
                Push-Location $repoRoot
                git pull --ff-only 2>&1 | Out-Null
                git add 'data/instagram.json' 2>&1 | Out-Null
                $changed = -not [string]::IsNullOrWhiteSpace((git status --porcelain 'data/instagram.json' | Out-String))
                if ($changed) {
                    git commit -m "Instagram 일일 브리프 갱신 ($today)" 2>&1 | Out-Null
                    git push 2>&1 | Out-Null
                    $pushed = $true
                }
            } catch {
                Write-Warning "대시보드 자동 반영(git push) 실패: $($_.Exception.Message)"
            } finally {
                Pop-Location
            }
        }
    }

    Save-InstagramBriefState -State @{ followers = $followers; date = $today }

    Write-Host ''
    Write-Host '=== 오늘의 브리프 ===' -ForegroundColor Green
    Write-Host ("계정명   : {0}" -f $igProfile.username)
    Write-Host ("팔로워   : {0}명 ({1})" -f $followers, $deltaText)
    Write-Host ("요약     : {0}" -f $summary)
    Write-Host ("로컬 파일: {0}" -f $briefMdPath)
    if ($repoRoot) {
        Write-Host ("대시보드 : {0}" -f (if ($pushed) { '자동 반영 완료 (git push)' } else { '변경 없음 또는 반영 대기' }))
    }
}
catch {
    Write-Host '브리프 생성 실패' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
finally {
    $token = $null
    [System.GC]::Collect()
}
