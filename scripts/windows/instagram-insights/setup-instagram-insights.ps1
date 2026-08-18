<#
    setup-instagram-insights.ps1

    Run this ONCE per Windows user account (re-run any time to rotate credentials).

    What it does:
      1. Opens a local, masked-input Windows Forms window so you type your
         Instagram access token and app secret yourself. Neither value is ever
         printed, logged, or written to disk in plain text.
      2. Exchanges the short-lived token for a long-lived (~60 day) token via
         graph.instagram.com.
      3. Calls graph.instagram.com/me to confirm the connection.
      4. Checks which permissions the token actually carries
         (instagram_business_basic, instagram_business_manage_insights).
      5. Encrypts the long-lived token and app secret with Windows DPAPI
         (CurrentUser scope, i.e. only your Windows login can decrypt them)
         and saves them to:
           $env:LOCALAPPDATA\InstagramCodexConnector\config.json
      6. Registers a daily Scheduled Task that renews the token automatically
         once it is within 10 days of expiring.

    Nothing here is uploaded anywhere. All calls go directly from this machine
    to graph.instagram.com over HTTPS.

    Usage (from an ordinary, non-admin PowerShell prompt):
        powershell -ExecutionPolicy Bypass -File .\setup-instagram-insights.ps1
#>

[CmdletBinding()]
param(
    # Skip registering the auto-renew scheduled task (useful for re-runs).
    [switch]$SkipScheduledTask
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # keep Invoke-RestMethod quiet, no progress bar noise

# ---------------------------------------------------------------------------
# Paths — always derived from environment variables, never hard-coded users.
# ---------------------------------------------------------------------------
$ConnectorDir  = Join-Path $env:LOCALAPPDATA 'InstagramCodexConnector'
$ConfigPath    = Join-Path $ConnectorDir 'config.json'
$ReportsDir    = Join-Path $ConnectorDir 'reports'
$LogPath       = Join-Path $ConnectorDir 'connector.log'
$RenewScript   = Join-Path $PSScriptRoot 'renew-instagram-token.ps1'
$TaskName      = 'InstagramCodexConnector-TokenRenew'

New-Item -ItemType Directory -Path $ConnectorDir -Force | Out-Null
New-Item -ItemType Directory -Path $ReportsDir -Force | Out-Null

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path $LogPath -Value $line
}

function Protect-Secret {
    <# DPAPI-encrypt a plain string for the current Windows user only. #>
    param([Parameter(Mandatory)][string]$PlainText)
    Add-Type -AssemblyName System.Security
    $entropy = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($entropy)
    $plainBytes = [System.Text.Encoding]::UTF8.GetBytes($PlainText)
    $cipherBytes = [System.Security.Cryptography.ProtectedData]::Protect(
        $plainBytes, $entropy, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
    [pscustomobject]@{
        cipher  = [Convert]::ToBase64String($cipherBytes)
        entropy = [Convert]::ToBase64String($entropy)
    }
}

# ---------------------------------------------------------------------------
# Step 1 — local secure input window (values live only in memory here).
# ---------------------------------------------------------------------------
function Read-SecretsFromWindow {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $form                 = New-Object System.Windows.Forms.Form
    $form.Text            = 'Instagram Codex Connector — 자격 증명 입력'
    $form.Size            = New-Object System.Drawing.Size(460, 240)
    $form.StartPosition   = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox     = $false
    $form.MinimizeBox     = $false
    $form.TopMost         = $true

    $lblToken = New-Object System.Windows.Forms.Label
    $lblToken.Text = 'Instagram 액세스 토큰:'
    $lblToken.Location = New-Object System.Drawing.Point(15, 20)
    $lblToken.AutoSize = $true

    $txtToken = New-Object System.Windows.Forms.TextBox
    $txtToken.Location = New-Object System.Drawing.Point(15, 45)
    $txtToken.Size = New-Object System.Drawing.Size(410, 24)
    $txtToken.UseSystemPasswordChar = $true

    $lblSecret = New-Object System.Windows.Forms.Label
    $lblSecret.Text = 'Instagram 앱 시크릿:'
    $lblSecret.Location = New-Object System.Drawing.Point(15, 85)
    $lblSecret.AutoSize = $true

    $txtSecret = New-Object System.Windows.Forms.TextBox
    $txtSecret.Location = New-Object System.Drawing.Point(15, 110)
    $txtSecret.Size = New-Object System.Drawing.Size(410, 24)
    $txtSecret.UseSystemPasswordChar = $true

    $lblNote = New-Object System.Windows.Forms.Label
    $lblNote.Text = '입력값은 이 창을 벗어나지 않으며, 화면에 표시되지 않습니다.'
    $lblNote.Location = New-Object System.Drawing.Point(15, 145)
    $lblNote.AutoSize = $true
    $lblNote.ForeColor = [System.Drawing.Color]::Gray

    $btnOk = New-Object System.Windows.Forms.Button
    $btnOk.Text = '확인'
    $btnOk.Location = New-Object System.Drawing.Point(265, 165)
    $btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Text = '취소'
    $btnCancel.Location = New-Object System.Drawing.Point(350, 165)
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel

    $form.AcceptButton = $btnOk
    $form.CancelButton = $btnCancel
    $form.Controls.AddRange(@($lblToken, $txtToken, $lblSecret, $txtSecret, $lblNote, $btnOk, $btnCancel))

    $result = $form.ShowDialog()
    if ($result -ne [System.Windows.Forms.DialogResult]::OK) {
        throw '사용자가 입력을 취소했습니다.'
    }
    if ([string]::IsNullOrWhiteSpace($txtToken.Text) -or [string]::IsNullOrWhiteSpace($txtSecret.Text)) {
        throw '토큰과 앱 시크릿을 모두 입력해야 합니다.'
    }

    [pscustomobject]@{
        AccessToken = $txtToken.Text.Trim()
        AppSecret   = $txtSecret.Text.Trim()
    }
}

Write-Log 'Setup started.'
$secrets = Read-SecretsFromWindow
Write-Log 'Credentials captured from local input window (values not logged).'

try {
    # -----------------------------------------------------------------
    # Step 2 — exchange for a long-lived token.
    # -----------------------------------------------------------------
    $exchangeUri = 'https://graph.instagram.com/access_token' +
        '?grant_type=ig_exchange_token' +
        '&client_secret=' + [uri]::EscapeDataString($secrets.AppSecret) +
        '&access_token=' + [uri]::EscapeDataString($secrets.AccessToken)

    $exchangeResponse = Invoke-RestMethod -Method Get -Uri $exchangeUri
    $longLivedToken = $exchangeResponse.access_token
    $expiresInSec   = [int]$exchangeResponse.expires_in
    if (-not $longLivedToken) { throw '장기 액세스 토큰 교환 응답에 access_token이 없습니다.' }

    $issuedAtUtc  = (Get-Date).ToUniversalTime()
    $expiresAtUtc = $issuedAtUtc.AddSeconds($expiresInSec)
    Write-Log 'Long-lived token exchange succeeded.'

    # -----------------------------------------------------------------
    # Step 3 — test the connection against the real account.
    # -----------------------------------------------------------------
    $meUri = 'https://graph.instagram.com/me' +
        '?fields=id,username,account_type,media_count' +
        '&access_token=' + [uri]::EscapeDataString($longLivedToken)
    $igProfile = Invoke-RestMethod -Method Get -Uri $meUri
    Write-Log ("Connection test succeeded for user id {0}." -f $igProfile.id)

    # -----------------------------------------------------------------
    # Step 4 — check granted permissions.
    # -----------------------------------------------------------------
    $requiredPermissions = @('instagram_business_basic', 'instagram_business_manage_insights')
    $grantedPermissions = @()
    try {
        $permUri = 'https://graph.instagram.com/me/permissions' +
            '?access_token=' + [uri]::EscapeDataString($longLivedToken)
        $permResponse = Invoke-RestMethod -Method Get -Uri $permUri
        $grantedPermissions = $permResponse.data |
            Where-Object { $_.status -eq 'granted' } |
            Select-Object -ExpandProperty permission
    } catch {
        Write-Log 'permissions endpoint unavailable, falling back to functional checks.'
        # Functional fallback: a successful /me call already proves basic access.
        $grantedPermissions += 'instagram_business_basic'
        try {
            $insightsProbeUri = 'https://graph.instagram.com/{0}/insights?metric=reach&period=day&access_token={1}' -f `
                $igProfile.id, [uri]::EscapeDataString($longLivedToken)
            Invoke-RestMethod -Method Get -Uri $insightsProbeUri | Out-Null
            $grantedPermissions += 'instagram_business_manage_insights'
        } catch {
            Write-Log 'instagram_business_manage_insights probe failed.'
        }
    }
    $missingPermissions = $requiredPermissions | Where-Object { $_ -notin $grantedPermissions }

    # -----------------------------------------------------------------
    # Step 5 — DPAPI-encrypt and persist config (current Windows user only).
    # -----------------------------------------------------------------
    $encToken  = Protect-Secret -PlainText $longLivedToken
    $encSecret = Protect-Secret -PlainText $secrets.AppSecret

    $config = [ordered]@{
        schemaVersion       = 1
        userId              = $igProfile.id
        username            = $igProfile.username
        accountType         = $igProfile.account_type
        issuedAtUtc         = $issuedAtUtc.ToString('o')
        expiresAtUtc        = $expiresAtUtc.ToString('o')
        grantedPermissions  = @($grantedPermissions | Sort-Object -Unique)
        accessToken         = [ordered]@{ cipher = $encToken.cipher; entropy = $encToken.entropy }
        appSecret           = [ordered]@{ cipher = $encSecret.cipher; entropy = $encSecret.entropy }
    }
    $config | ConvertTo-Json -Depth 6 | Set-Content -Path $ConfigPath -Encoding UTF8

    # Restrict the config file to the current user only.
    icacls $ConfigPath /inheritance:r | Out-Null
    icacls $ConfigPath /grant:r ("$($env:USERDOMAIN)\$($env:USERNAME):(R,W)") | Out-Null

    Write-Log 'Config saved and ACL restricted to current user.'

    # -----------------------------------------------------------------
    # Step 6 — register the auto-renew scheduled task (10 days before expiry).
    # -----------------------------------------------------------------
    if (-not $SkipScheduledTask) {
        if (-not (Test-Path $RenewScript)) {
            Write-Log "WARNING: renew-instagram-token.ps1 not found next to setup script at $RenewScript; skipping task registration."
        } else {
            $action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RenewScript`""
            schtasks /Create /TN $TaskName /TR $action /SC DAILY /ST 09:00 /RU $env:USERNAME /IT /F | Out-Null
            Write-Log "Scheduled task '$TaskName' registered (daily, runs only when logged on)."
        }
    }

    # -----------------------------------------------------------------
    # Step 9/10 — report only non-secret facts.
    # -----------------------------------------------------------------
    Write-Host ''
    Write-Host '=== Instagram Codex Connector — 설정 완료 ===' -ForegroundColor Green
    Write-Host ("계정명(username): {0}" -f $igProfile.username)
    Write-Host ("연결 성공 여부   : 성공")
    Write-Host ("토큰 만료일(UTC) : {0}" -f $expiresAtUtc.ToString('yyyy-MM-dd HH:mm'))
    Write-Host ("권한 확인        : instagram_business_basic={0}, instagram_business_manage_insights={1}" -f `
        ('instagram_business_basic' -in $grantedPermissions), ('instagram_business_manage_insights' -in $grantedPermissions))
    if ($missingPermissions) {
        Write-Host ("경고: 다음 권한이 없습니다 -> {0}" -f ($missingPermissions -join ', ')) -ForegroundColor Yellow
    }
    Write-Host ("설정 파일        : {0}" -f $ConfigPath)
    Write-Host ''
}
catch {
    Write-Log ("ERROR: " + $_.Exception.Message)
    Write-Host ''
    Write-Host '=== Instagram Codex Connector — 연결 실패 ===' -ForegroundColor Red
    Write-Host ("사유: {0}" -f $_.Exception.Message)
    Write-Host ''
    throw
}
finally {
    Remove-Variable secrets -ErrorAction SilentlyContinue
    Remove-Variable longLivedToken -ErrorAction SilentlyContinue
    [System.GC]::Collect()
}
