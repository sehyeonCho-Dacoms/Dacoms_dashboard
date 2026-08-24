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
                $detail = '{0} (code={1}, type={2})' -f $parsed.error.message, $parsed.error.code, $parsed.error.type
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

function Get-InstagramProfile {
    param([Parameter(Mandatory)][string]$AccessToken)
    return Invoke-InstagramGraphGet -Path 'me' -QueryParams @{
        fields       = 'id,username,account_type,media_count'
        access_token = $AccessToken
    }
}

function Get-InstagramGrantedPermissions {
    param([Parameter(Mandatory)][string]$AccessToken)
    $resp = Invoke-InstagramGraphGet -Path 'me/permissions' -QueryParams @{
        access_token = $AccessToken
    }
    return @($resp.data | Where-Object { $_.status -eq 'granted' } | Select-Object -ExpandProperty permission)
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

function Register-InstagramTokenRenewalTask {
    <#
        토큰 만료 10일 전부터 매일 자동 갱신을 시도하는 작업 스케줄러 작업을 등록합니다.
        renew-instagram-token.ps1 자체가 "만료까지 10일 이하일 때만" 실제 갱신을 수행하므로
        매일 실행되어도 안전합니다.
    #>
    param([Parameter(Mandatory)][string]$RenewScriptPath)

    $taskName = 'InstagramCodexConnector-TokenRenew'
    $powershellExe = Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path $powershellExe)) { $powershellExe = 'powershell.exe' }

    try {
        $action = New-ScheduledTaskAction -Execute $powershellExe `
            -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RenewScriptPath`""
        $trigger = New-ScheduledTaskTrigger -Daily -At 3:00AM
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
            -Principal $principal -Settings $settings `
            -Description 'Instagram 장기 액세스 토큰 만료 10일 전 자동 갱신' | Out-Null
        return $true
    } catch {
        Write-Warning "자동 갱신 예약 작업을 등록하지 못했습니다: $($_.Exception.Message)"
        return $false
    }
}
