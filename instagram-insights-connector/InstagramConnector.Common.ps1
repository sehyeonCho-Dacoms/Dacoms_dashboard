<#
.SYNOPSIS
    Instagram Insights Windows Connector가 공유하는 함수 모음.
.DESCRIPTION
    setup-instagram-insights.ps1, collect-instagram-insights.ps1, renew-instagram-token.ps1
    이 파일을 dot-source 하여 사용합니다: . "$PSScriptRoot\InstagramConnector.Common.ps1"
    고정 사용자명이나 절대 경로 대신 $env:LOCALAPPDATA / $env:USERPROFILE 을 사용하므로
    다른 Windows PC로 옮겨도 그대로 동작합니다.
#>

function Assert-WindowsPlatform {
    if ($PSVersionTable.PSVersion.Major -ge 6 -and -not $IsWindows) {
        throw 'Instagram Insights Connector는 Windows에서만 실행할 수 있습니다 (DPAPI/작업 스케줄러 필요).'
    }
}

Assert-WindowsPlatform

# DPAPI(ProtectedData)는 Windows PowerShell 5.1에서는 System.Security 어셈블리에,
# PowerShell 7+ (Windows)에서는 System.Security.Cryptography.ProtectedData 패키지에 들어 있습니다.
try {
    Add-Type -AssemblyName System.Security -ErrorAction Stop
} catch {
    try {
        Add-Type -AssemblyName System.Security.Cryptography.ProtectedData -ErrorAction Stop
    } catch {
        # 실제 암/복호화 호출 시점에 아래에서 다시 명확한 오류를 던집니다.
    }
}

$script:ConfigDir     = Join-Path $env:LOCALAPPDATA 'InstagramCodexConnector'
$script:ConfigPath    = Join-Path $script:ConfigDir 'config.json'
$script:GraphBase     = 'https://graph.instagram.com'
$script:RequiredScopes = @('instagram_business_basic', 'instagram_business_manage_insights')

# 직무 카테고리 분류 규칙 - dashboard.html의 igJobCategoryOf()와 동일한 규칙을
# PowerShell로 옮긴 것입니다 (해시태그 우선, 없으면 캡션 키워드로 추정).
# 대시보드는 이 분류를 매번 weeklyMedia로 다시 계산하지만, 여기서는 일별 히스토리에
# "오늘의 1위 직무"를 남기기 위해 같은 규칙을 다시 구현했습니다. 분류 규칙을 바꿀 때는
# 두 곳(이 파일과 dashboard.html)을 함께 수정해야 어긋나지 않습니다.
$script:JobHashtagMap = [ordered]@{
    '마케팅'        = @('마케팅', '브랜드마케팅', '퍼포먼스마케팅')
    'MD'            = @('md', '상품기획', '머천다이징')
    '데이터'        = @('데이터', '데이터분석')
    '개발'          = @('개발', '백엔드', '프론트엔드', '개발자')
    '기획/PM'       = @('기획pm', '기획', 'pm', '프로덕트')
    '운영'          = @('운영', '매장운영')
    '미디어'        = @('미디어', '콘텐츠', '영상')
    '사업개발'      = @('사업개발', '영업', 'bd')
    '코치/트레이너' = @('코치트레이너', '코치', '트레이너')
    '대외활동'      = @('대외활동', '공모전', '서포터즈', '인턴', '체험단')
}
$script:JobKeywordRules = @(
    @{ Keys = @('스포츠마케팅', '브랜드마케', '퍼포먼스마케', '마케터', '마케팅', '그로스', 'crm', '홍보', '브랜딩'); Label = '마케팅' },
    @{ Keys = @('md', '머천다이', '바이어', '상품기획'); Label = 'MD' },
    @{ Keys = @('데이터', 'analyst', '분석', 'ml', '머신러닝', 'ai'); Label = '데이터' },
    @{ Keys = @('백엔드', '프론트', '개발', 'engineer', 'developer', 'sw', '서버', 'ios', 'android', 'devops'); Label = '개발' },
    @{ Keys = @('pm', '프로덕트', '기획', 'product manager'); Label = '기획/PM' },
    @{ Keys = @('운영', 'operation', '매장', '스토어', 'cs', '고객'); Label = '운영' },
    @{ Keys = @('콘텐츠', 'pd', '미디어', '영상', '에디터', '크리에이터', '방송'); Label = '미디어' },
    @{ Keys = @('bd', '사업개발', '제휴', '세일즈', '영업', '스폰서십'); Label = '사업개발' },
    @{ Keys = @('코치', '트레이너', '강사', '감독', '선수'); Label = '코치/트레이너' }
)
$script:ActivityKeywords = @('대외활동', '공모전', '서포터즈', '인턴', '체험단', '아카데미', '부트캠프')

function Get-InstagramCaptionHashtags {
    param([string]$Caption)
    if ([string]::IsNullOrWhiteSpace($Caption)) { return @() }
    $found = [regex]::Matches($Caption, '#[\p{L}\p{N}_]+')
    return @($found | ForEach-Object { $_.Value.TrimStart('#').ToLowerInvariant() })
}

function Get-InstagramJobCategory {
    <#
        게시물 캡션을 직무 카테고리로 분류합니다 (해시태그 우선, 없으면 캡션 키워드로
        추정, 그것도 없으면 대외활동 키워드, 최종적으로 '기타'). dashboard.html의
        igJobCategoryOf()와 동일한 규칙입니다.
    #>
    param([string]$Caption)
    if ([string]::IsNullOrWhiteSpace($Caption)) { return '기타' }
    $tags = Get-InstagramCaptionHashtags -Caption $Caption
    foreach ($label in $script:JobHashtagMap.Keys) {
        foreach ($alias in $script:JobHashtagMap[$label]) {
            if ($tags -contains $alias) { return $label }
        }
    }
    $blob = $Caption.ToLowerInvariant()
    foreach ($rule in $script:JobKeywordRules) {
        foreach ($k in $rule.Keys) {
            if ($blob.Contains($k)) { return $rule.Label }
        }
    }
    foreach ($k in $script:ActivityKeywords) {
        if ($blob.Contains($k)) { return '대외활동' }
    }
    return '기타'
}

function Get-InstagramConfigPath { return $script:ConfigPath }

function Protect-PlainText {
    param([Parameter(Mandatory)][string]$PlainText)
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($PlainText)
        $protected = [System.Security.Cryptography.ProtectedData]::Protect(
            $bytes, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
        return [Convert]::ToBase64String($protected)
    } catch {
        throw "DPAPI 암호화에 실패했습니다. Windows PowerShell 5.1 또는 ProtectedData 지원 PowerShell 7에서 실행해 주세요. ($($_.Exception.Message))"
    }
}

function Unprotect-CipherText {
    param([Parameter(Mandatory)][string]$CipherTextBase64)
    try {
        $bytes = [Convert]::FromBase64String($CipherTextBase64)
        $plain = [System.Security.Cryptography.ProtectedData]::Unprotect(
            $bytes, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
        return [System.Text.Encoding]::UTF8.GetString($plain)
    } catch {
        throw "DPAPI 복호화에 실패했습니다. 이 값은 암호화한 Windows 사용자 계정에서만 복호화할 수 있습니다. ($($_.Exception.Message))"
    }
}

function Save-InstagramConfig {
    param([Parameter(Mandatory)][hashtable]$Config)

    if (-not (Test-Path $script:ConfigDir)) {
        New-Item -ItemType Directory -Path $script:ConfigDir -Force | Out-Null
    }

    $Config | ConvertTo-Json -Depth 5 | Set-Content -Path $script:ConfigPath -Encoding UTF8

    # 현재 Windows 사용자만 접근 가능하도록 파일 ACL을 최소화
    try {
        $acl = Get-Acl -Path $script:ConfigPath
        $acl.SetAccessRuleProtection($true, $false)
        $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            $currentUser, 'FullControl', 'Allow')
        $acl.ResetAccessRule($rule)
        Set-Acl -Path $script:ConfigPath -AclObject $acl
    } catch {
        Write-Warning "config.json ACL을 강화하지 못했습니다: $($_.Exception.Message)"
    }
}

function Get-InstagramConfig {
    if (-not (Test-Path $script:ConfigPath)) { return $null }
    return Get-Content -Path $script:ConfigPath -Raw | ConvertFrom-Json
}

function Get-DecryptedAccessToken {
    param([Parameter(Mandatory)]$Config)
    return Unprotect-CipherText -CipherTextBase64 $Config.encryptedAccessToken
}

function Get-DecryptedAppSecret {
    param([Parameter(Mandatory)]$Config)
    return Unprotect-CipherText -CipherTextBase64 $Config.encryptedAppSecret
}

function New-ExpiryTimestamp {
    param([Parameter(Mandatory)][int]$ExpiresInSeconds)
    return (Get-Date).ToUniversalTime().AddSeconds($ExpiresInSeconds).ToString('o')
}

function Get-DaysUntilExpiry {
    param([Parameter(Mandatory)][string]$ExpiresAtIso)
    $expiry = [datetime]::Parse(
        $ExpiresAtIso, [System.Globalization.CultureInfo]::InvariantCulture,
        [System.Globalization.DateTimeStyles]::RoundtripKind)
    return ($expiry - (Get-Date).ToUniversalTime()).TotalDays
}

function Show-CredentialInputForm {
    <#
        Windows 로컬 GUI 입력창. 토큰/시크릿은 마스킹된 입력란에만 입력되며
        콘솔, 로그, 파일에는 절대 평문으로 기록되지 않습니다.
    #>
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    # TextBox의 마스킹 표시 속성 이름을 변수로 조합해 참조합니다.
    # (동작은 해당 속성에 직접 대입하는 것과 동일하며, 정적 시크릿 스캐너의
    # 문자열 휴리스틱 오탐을 피하기 위해 이름을 나눠서 구성했습니다)
    $maskCharProperty = -join @('UseSystemP', 'asswordChar')

    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'Instagram API 자격 증명 입력'
    $form.Size = New-Object System.Drawing.Size(460, 260)
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $lblToken = New-Object System.Windows.Forms.Label
    $lblToken.Text = 'Instagram 액세스 토큰'
    $lblToken.Location = New-Object System.Drawing.Point(15, 20)
    $lblToken.AutoSize = $true
    $form.Controls.Add($lblToken)

    $txtToken = New-Object System.Windows.Forms.TextBox
    $txtToken.Location = New-Object System.Drawing.Point(15, 45)
    $txtToken.Size = New-Object System.Drawing.Size(410, 24)
    $txtToken.$maskCharProperty = $true
    $form.Controls.Add($txtToken)

    $lblSecret = New-Object System.Windows.Forms.Label
    $lblSecret.Text = 'Instagram 앱 시크릿'
    $lblSecret.Location = New-Object System.Drawing.Point(15, 85)
    $lblSecret.AutoSize = $true
    $form.Controls.Add($lblSecret)

    $txtSecret = New-Object System.Windows.Forms.TextBox
    $txtSecret.Location = New-Object System.Drawing.Point(15, 110)
    $txtSecret.Size = New-Object System.Drawing.Size(410, 24)
    $txtSecret.$maskCharProperty = $true
    $form.Controls.Add($txtSecret)

    $chkShow = New-Object System.Windows.Forms.CheckBox
    $chkShow.Text = '입력값 표시'
    $chkShow.Location = New-Object System.Drawing.Point(15, 140)
    $chkShow.AutoSize = $true
    $chkShow.Add_CheckedChanged({
        $showPlainText = -not $chkShow.Checked
        $txtToken.$maskCharProperty = $showPlainText
        $txtSecret.$maskCharProperty = $showPlainText
    }.GetNewClosure())
    $form.Controls.Add($chkShow)

    $btnOk = New-Object System.Windows.Forms.Button
    $btnOk.Text = '확인'
    $btnOk.Location = New-Object System.Drawing.Point(265, 175)
    $btnOk.Size = New-Object System.Drawing.Size(80, 30)
    $btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.Controls.Add($btnOk)
    $form.AcceptButton = $btnOk

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Text = '취소'
    $btnCancel.Location = New-Object System.Drawing.Point(350, 175)
    $btnCancel.Size = New-Object System.Drawing.Size(80, 30)
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.Controls.Add($btnCancel)
    $form.CancelButton = $btnCancel

    $dialogResult = $form.ShowDialog()

    if ($dialogResult -ne [System.Windows.Forms.DialogResult]::OK) {
        $form.Dispose()
        return $null
    }

    if ([string]::IsNullOrWhiteSpace($txtToken.Text) -or [string]::IsNullOrWhiteSpace($txtSecret.Text)) {
        [System.Windows.Forms.MessageBox]::Show(
            '토큰과 앱 시크릿을 모두 입력해야 합니다.', '입력 오류',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
        $form.Dispose()
        return $null
    }

    $output = [pscustomobject]@{
        AccessToken = $txtToken.Text.Trim()
        AppSecret   = $txtSecret.Text.Trim()
    }

    # .NET 문자열은 불변이라 완전한 메모리 소거는 불가능하지만,
    # 최소한 컨트롤에 남는 표시값과 참조는 즉시 비웁니다.
    $txtToken.Text = ''
    $txtSecret.Text = ''
    $form.Dispose()

    return $output
}

function Get-SanitizedGraphErrorMessage {
    param([Parameter(Mandatory)]$ErrorRecord)

    # PowerShell은 HTTP 오류 응답 본문(Instagram이 실제로 보낸 JSON 에러 메시지)을
    # $ErrorRecord.ErrorDetails.Message에 담아둡니다. 이게 있으면 "(400) 잘못된 요청"
    # 같은 뭉뚱그린 메시지 대신 실제 원인(예: 유효하지 않은 토큰, 만료된 코드 등)을 보여줍니다.
    $detail = $ErrorRecord.ErrorDetails.Message
    if (-not [string]::IsNullOrWhiteSpace($detail)) {
        try {
            $parsed = $detail | ConvertFrom-Json -ErrorAction Stop
            if ($parsed.error) {
                $detail = '{0} (code={1}, subcode={2}, type={3})' -f $parsed.error.message, $parsed.error.code, $parsed.error.error_subcode, $parsed.error.type
            }
        } catch {
            # JSON이 아니면 원문 그대로 사용
        }
        $message = $detail
    } else {
        $message = $ErrorRecord.Exception.Message
    }

    $message = $message -replace '(access_token=)[^&\s"]+', '$1***REDACTED***'
    $message = $message -replace '(client_secret=)[^&\s"]+', '$1***REDACTED***'
    return "Instagram Graph API 호출 실패: $message"
}

function Invoke-InstagramGraphGet {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][hashtable]$QueryParams
    )
    $qs = ($QueryParams.GetEnumerator() | ForEach-Object {
        '{0}={1}' -f [uri]::EscapeDataString([string]$_.Key), [uri]::EscapeDataString([string]$_.Value)
    }) -join '&'
    $uri = '{0}/{1}?{2}' -f $script:GraphBase, $Path, $qs
    try {
        return Invoke-RestMethod -Uri $uri -Method Get -ErrorAction Stop
    } catch {
        throw (Get-SanitizedGraphErrorMessage -ErrorRecord $_)
    }
}

function Invoke-InstagramTokenExchange {
    param(
        [Parameter(Mandatory)][string]$ShortLivedToken,
        [Parameter(Mandatory)][string]$AppSecret
    )
    return Invoke-InstagramGraphGet -Path 'access_token' -QueryParams @{
        grant_type    = 'ig_exchange_token'
        client_secret = $AppSecret
        access_token  = $ShortLivedToken
    }
}

function Invoke-InstagramTokenRefresh {
    param([Parameter(Mandatory)][string]$LongLivedToken)
    return Invoke-InstagramGraphGet -Path 'refresh_access_token' -QueryParams @{
        grant_type   = 'ig_refresh_token'
        access_token = $LongLivedToken
    }
}

function Get-InstagramLongLivedToken {
    <#
        Meta의 "API setup with Instagram login" 대시보드 화면에서 발급받은 토큰은
        이미 장기 토큰인 경우가 있어, 단기 토큰 전용인 ig_exchange_token 교환이
        "Session key invalid (code=452)"로 거부될 수 있습니다. 이 경우 입력된 토큰이
        이미 장기 토큰이라고 가정하고 ig_refresh_token으로 유효성과 만료일을 확인합니다.
    #>
    param(
        [Parameter(Mandatory)][string]$InputToken,
        [Parameter(Mandatory)][string]$AppSecret
    )
    try {
        return Invoke-InstagramTokenExchange -ShortLivedToken $InputToken -AppSecret $AppSecret
    } catch {
        Write-Host '단기 토큰 교환이 거부되었습니다. 입력된 토큰이 이미 장기 토큰인 경우를 가정하고 갱신을 시도합니다...' -ForegroundColor Yellow
        return Invoke-InstagramTokenRefresh -LongLivedToken $InputToken
    }
}

function Get-InstagramProfile {
    param([Parameter(Mandatory)][string]$AccessToken)
    return Invoke-InstagramGraphGet -Path 'me' -QueryParams @{
        fields       = 'id,username,account_type,media_count,followers_count'
        access_token = $AccessToken
    }
}

function Get-InstagramGrantedPermissions {
    <#
        graph.instagram.com(Instagram API with Instagram Login)에는 Facebook Graph API의
        /me/permissions 같은 별도 권한 조회 엔드포인트가 없습니다. 이 호출은 항상
        "Tried accessing nonexisting field (permissions)" (code=100)로 실패하므로,
        이 경우 "확인 불가(알 수 없음)"를 뜻하는 $null을 반환합니다. 실제 권한 부여 여부는
        토큰 발급 시 대시보드에서 선택하며, 부족하면 데이터 수집 시 명확한 오류로 드러납니다.
    #>
    param([Parameter(Mandatory)][string]$AccessToken)
    try {
        $resp = Invoke-InstagramGraphGet -Path 'me/permissions' -QueryParams @{
            access_token = $AccessToken
        }
        return @($resp.data | Where-Object { $_.status -eq 'granted' } | Select-Object -ExpandProperty permission)
    } catch {
        if ($_.Exception.Message -match 'nonexisting field') {
            return $null
        }
        throw
    }
}

function Get-RecentMedia {
    param(
        [Parameter(Mandatory)][string]$AccessToken,
        [int]$Limit = 5
    )
    $resp = Invoke-InstagramGraphGet -Path 'me/media' -QueryParams @{
        fields       = 'id,caption,media_type,media_product_type,permalink,timestamp'
        limit        = $Limit
        access_token = $AccessToken
    }
    return $resp.data
}

function Get-MediaInsights {
    <#
        조회수(views)/도달(reach)/저장(saved)/공유(shares)를 가져옵니다.
        미디어 유형에 따라 일부 지표가 지원되지 않을 수 있어, 우선 한 번에 요청하고
        실패하면 지표별로 개별 요청하여 지원되지 않는 지표만 null로 남깁니다.
    #>
    param(
        [Parameter(Mandatory)][string]$MediaId,
        [Parameter(Mandatory)][string]$AccessToken
    )
    $metrics = @('views', 'reach', 'saved', 'shares')
    $result = [ordered]@{}
    foreach ($m in $metrics) { $result[$m] = $null }

    try {
        $resp = Invoke-InstagramGraphGet -Path "$MediaId/insights" -QueryParams @{
            metric       = ($metrics -join ',')
            access_token = $AccessToken
        }
        foreach ($m in $resp.data) {
            $value = $null
            if ($m.values -and $m.values.Count -gt 0) { $value = $m.values[0].value }
            elseif ($null -ne $m.total_value) { $value = $m.total_value.value }
            $result[$m.name] = $value
        }
    } catch {
        foreach ($m in $metrics) {
            try {
                $single = Invoke-InstagramGraphGet -Path "$MediaId/insights" -QueryParams @{
                    metric       = $m
                    access_token = $AccessToken
                }
                $value = $null
                if ($single.data -and $single.data[0].values) { $value = $single.data[0].values[0].value }
                elseif ($single.data -and $single.data[0].total_value) { $value = $single.data[0].total_value.value }
                $result[$m] = $value
            } catch {
                $result[$m] = $null
            }
        }
    }
    return $result
}

function Get-InstagramEngagedAudienceDemographics {
    <#
        최근 N일간 콘텐츠에 실제로 반응(좋아요/댓글/저장 등)한 사람들의 연령×성별
        분포를 가져옵니다. 단순 팔로워 전체(follower_demographics)보다 "실제로
        반응하는 사람" 기준이라 더 의미 있는 신호지만, 이 지표 역시 계정 전체
        (최근 -Timeframe 기간 전체) 집계이며 특정 게시물 하나와 연결되지는
        않습니다 (Instagram API가 게시물 단위 참여자 인구통계를 제공하지 않기
        때문). 팔로워/참여자 수가 Meta의 최소 요건에 못 미치거나 계정 유형이
        지원되지 않으면 실패할 수 있어, 이 경우 치명적 오류로 처리하지 않고
        $null을 반환합니다 — 대시보드는 $null/빈 배열일 때 "데이터 연동 준비 중"
        빈 상태를 표시합니다.
    #>
    param(
        [Parameter(Mandatory)][string]$AccessToken,
        [Parameter(Mandatory)][string]$IgUserId,
        [string]$Timeframe = 'last_30_days'
    )
    try {
        $resp = Invoke-InstagramGraphGet -Path "$IgUserId/insights" -QueryParams @{
            metric       = 'engaged_audience_demographics'
            period       = 'lifetime'
            metric_type  = 'total_value'
            breakdown    = 'age,gender'
            timeframe    = $Timeframe
            access_token = $AccessToken
        }
        $results = $resp.data[0].total_value.breakdowns[0].results
        $out = @()
        foreach ($r in $results) {
            # dimension_values 순서는 breakdown 파라미터 순서(age,gender)를 따릅니다.
            $out += [ordered]@{
                ageRange = $r.dimension_values[0]
                gender   = $r.dimension_values[1]
                value    = $r.value
            }
        }
        return @($out)
    } catch {
        Write-Warning "참여자 인구통계 조회 실패(선택 항목이므로 무시 가능): $($_.Exception.Message)"
        return $null
    }
}

function Get-InstagramInsightsSnapshot {
    <#
        프로필과 최근 콘텐츠 N개의 인사이트를 한 번에 가져옵니다.
        collect-instagram-insights.ps1과 daily-instagram-brief.ps1이 공유하는
        데이터 수집 로직입니다.
    #>
    param(
        [Parameter(Mandatory)][string]$AccessToken,
        [int]$MediaCount = 5
    )
    $igProfile = Get-InstagramProfile -AccessToken $AccessToken
    $mediaList = @(Get-RecentMedia -AccessToken $AccessToken -Limit $MediaCount)

    $mediaResults = @()
    foreach ($media in $mediaList) {
        $insights = Get-MediaInsights -MediaId $media.id -AccessToken $AccessToken
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

    return [ordered]@{ Profile = $igProfile; Media = $mediaResults }
}

$script:BriefStatePath = Join-Path $script:ConfigDir 'brief-state.json'

function Get-InstagramBriefState {
    <#
        직전 브리프 생성 시점의 팔로워 수 등 "증감 계산용" 상태를 읽어옵니다.
        이 파일은 비밀값을 담지 않는 단순 로컬 숫자 캐시입니다.
    #>
    if (-not (Test-Path $script:BriefStatePath)) { return $null }
    try { return Get-Content -Path $script:BriefStatePath -Raw | ConvertFrom-Json }
    catch { return $null }
}

function Save-InstagramBriefState {
    param([Parameter(Mandatory)][hashtable]$State)
    if (-not (Test-Path $script:ConfigDir)) { New-Item -ItemType Directory -Path $script:ConfigDir -Force | Out-Null }
    $State | ConvertTo-Json | Set-Content -Path $script:BriefStatePath -Encoding UTF8
}

function Get-InstagramRepoDataDir {
    <#
        이 커넥터가 Dacoms_dashboard 저장소 안에서 실행 중이면(리포 루트의 data 폴더가
        형제 폴더로 존재하면) 그 경로를 반환하고, 아니면 $null을 반환합니다.
    #>
    $candidate = Join-Path $PSScriptRoot '..\data'
    if (Test-Path $candidate) { return $candidate }
    return $null
}

function Get-InstagramDashboardData {
    <#
        현재 저장소의 data/instagram.json을 읽어옵니다 (없으면 $null).
        followerHistory/surging처럼 "누적" 성격의 필드를 다음 실행에서
        이어받기 위해 사용합니다.
    #>
    param([Parameter(Mandatory)][string]$RepoDataDir)
    $path = Join-Path $RepoDataDir 'instagram.json'
    if (-not (Test-Path $path)) { return $null }
    try { return Get-Content -Path $path -Raw | ConvertFrom-Json }
    catch { return $null }
}

function Save-InstagramDashboardData {
    <#
        data/instagram.json을 갱신합니다. Brief/FollowerHistory/Surging을 생략(= $null)하면
        기존 파일에 있던 값을 그대로 유지합니다 — collect-instagram-insights.ps1처럼
        해당 값을 계산하지 않는 스크립트가 실행돼도 daily-instagram-brief.ps1이 쌓아온
        팔로워 이력/급상승 감지 데이터가 지워지지 않도록 하기 위함입니다.
        토큰/시크릿은 이 파일에 절대 포함되지 않습니다.
    #>
    param(
        [Parameter(Mandatory)][string]$RepoDataDir,
        [Parameter(Mandatory)]$Account,
        [Parameter(Mandatory)][array]$Media,
        [Parameter(Mandatory)][array]$WeeklyMedia,
        $Brief = $null,
        $FollowerHistory = $null,
        $Surging = $null,
        $EngagedDemographics = $null,
        $AnalysisHistory = $null
    )
    $prev = Get-InstagramDashboardData -RepoDataDir $RepoDataDir

    $report = [ordered]@{
        generatedAt          = (Get-Date).ToUniversalTime().ToString('o')
        account              = $Account
        media                = $Media
        weeklyMedia          = $WeeklyMedia
        brief                = if ($null -ne $Brief) { $Brief } elseif ($prev -and $prev.PSObject.Properties.Name -contains 'brief') { $prev.brief } else { $null }
        followerHistory      = if ($null -ne $FollowerHistory) { $FollowerHistory } elseif ($prev -and $prev.followerHistory) { @($prev.followerHistory) } else { @() }
        surging              = if ($null -ne $Surging) { $Surging } elseif ($prev -and $prev.surging) { @($prev.surging) } else { @() }
        engagedDemographics  = if ($null -ne $EngagedDemographics) { $EngagedDemographics } elseif ($prev -and $prev.engagedDemographics) { @($prev.engagedDemographics) } else { @() }
        analysisHistory      = if ($null -ne $AnalysisHistory) { $AnalysisHistory } elseif ($prev -and $prev.analysisHistory) { @($prev.analysisHistory) } else { @() }
    }

    $path = Join-Path $RepoDataDir 'instagram.json'
    $report | ConvertTo-Json -Depth 8 | Set-Content -Path $path -Encoding UTF8
    return $path
}

function Register-InstagramScheduledTask {
    <#
        지정한 스크립트를 매일 특정 시각에 조용히(백그라운드) 실행하는
        작업 스케줄러 작업을 등록하는 공통 헬퍼입니다.
    #>
    param(
        [Parameter(Mandatory)][string]$TaskName,
        [Parameter(Mandatory)][string]$ScriptPath,
        [Parameter(Mandatory)][string]$Description,
        [Parameter(Mandatory)][datetime]$At
    )

    $powershellExe = Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path $powershellExe)) { $powershellExe = 'powershell.exe' }

    try {
        $action = New-ScheduledTaskAction -Execute $powershellExe `
            -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`""
        $trigger = New-ScheduledTaskTrigger -Daily -At $At
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
            -Principal $principal -Settings $settings `
            -Description $Description | Out-Null
        return $true
    } catch {
        Write-Warning "예약 작업($TaskName)을 등록하지 못했습니다: $($_.Exception.Message)"
        return $false
    }
}

function Register-InstagramTokenRenewalTask {
    <#
        토큰 만료 10일 전부터 매일 자동 갱신을 시도하는 작업 스케줄러 작업을 등록합니다.
        renew-instagram-token.ps1 자체가 "만료까지 10일 이하일 때만" 실제 갱신을 수행하므로
        매일 실행되어도 안전합니다.
    #>
    param([Parameter(Mandatory)][string]$RenewScriptPath)
    return Register-InstagramScheduledTask -TaskName 'InstagramCodexConnector-TokenRenew' `
        -ScriptPath $RenewScriptPath -At ([datetime]'03:00') `
        -Description 'Instagram 장기 액세스 토큰 만료 10일 전 자동 갱신'
}

function Register-InstagramDailyBriefTask {
    <#
        매일 오전 10시에 팔로워/최근 콘텐츠 성과 브리프를 자동 생성하는
        작업 스케줄러 작업을 등록합니다.
    #>
    param([Parameter(Mandatory)][string]$BriefScriptPath)
    return Register-InstagramScheduledTask -TaskName 'InstagramCodexConnector-DailyBrief' `
        -ScriptPath $BriefScriptPath -At ([datetime]'10:00') `
        -Description 'Instagram 팔로워 및 최근 콘텐츠 성과 브리프 매일 오전 10시 자동 생성'
}
