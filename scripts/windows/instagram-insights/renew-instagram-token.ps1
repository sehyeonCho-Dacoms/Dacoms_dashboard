<#
    renew-instagram-token.ps1

    Called automatically by the daily "InstagramCodexConnector-TokenRenew"
    Scheduled Task that setup-instagram-insights.ps1 registers. Can also be
    run manually.

    Behavior:
      - Reads the encrypted config, decrypts the token in memory only.
      - If the token expires in more than 10 days, does nothing.
      - Otherwise calls graph.instagram.com/refresh_access_token, gets a
        fresh ~60 day token, re-encrypts it with DPAPI, and updates config.json.
      - Never prints or logs the token/secret values.
#>

[CmdletBinding()]
param(
    [int]$RenewThresholdDays = 10
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$ConnectorDir = Join-Path $env:LOCALAPPDATA 'InstagramCodexConnector'
$ConfigPath   = Join-Path $ConnectorDir 'config.json'
$LogPath      = Join-Path $ConnectorDir 'connector.log'

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

function Protect-Secret {
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

if (-not (Test-Path $ConfigPath)) {
    Write-Log 'renew: config.json not found, skipping (run setup-instagram-insights.ps1 first).'
    return
}

try {
    $config = Get-Content -Path $ConfigPath -Raw | ConvertFrom-Json
    $expiresAtUtc = [datetime]::Parse($config.expiresAtUtc, $null, [System.Globalization.DateTimeStyles]::RoundtripKind)
    $daysLeft = ($expiresAtUtc - (Get-Date).ToUniversalTime()).TotalDays

    if ($daysLeft -gt $RenewThresholdDays) {
        Write-Log ("renew: skipped, {0:N1} days remain (threshold {1})." -f $daysLeft, $RenewThresholdDays)
        return
    }

    $currentToken = Unprotect-Secret -Secret $config.accessToken

    $refreshUri = 'https://graph.instagram.com/refresh_access_token' +
        '?grant_type=ig_refresh_token' +
        '&access_token=' + [uri]::EscapeDataString($currentToken)
    $refreshResponse = Invoke-RestMethod -Method Get -Uri $refreshUri

    $newToken = $refreshResponse.access_token
    $expiresInSec = [int]$refreshResponse.expires_in
    if (-not $newToken) { throw 'refresh_access_token 응답에 access_token이 없습니다.' }

    $issuedAtUtc  = (Get-Date).ToUniversalTime()
    $newExpiresAtUtc = $issuedAtUtc.AddSeconds($expiresInSec)

    $encToken = Protect-Secret -PlainText $newToken
    $config.accessToken = [ordered]@{ cipher = $encToken.cipher; entropy = $encToken.entropy }
    $config.issuedAtUtc = $issuedAtUtc.ToString('o')
    $config.expiresAtUtc = $newExpiresAtUtc.ToString('o')

    $config | ConvertTo-Json -Depth 6 | Set-Content -Path $ConfigPath -Encoding UTF8
    icacls $ConfigPath /inheritance:r | Out-Null
    icacls $ConfigPath /grant:r ("$($env:USERDOMAIN)\$($env:USERNAME):(R,W)") | Out-Null

    Write-Log ("renew: succeeded, new expiry {0:yyyy-MM-dd HH:mm} UTC." -f $newExpiresAtUtc)
}
catch {
    Write-Log ("renew: ERROR " + $_.Exception.Message)
}
finally {
    Remove-Variable currentToken -ErrorAction SilentlyContinue
    Remove-Variable newToken -ErrorAction SilentlyContinue
    [System.GC]::Collect()
}
