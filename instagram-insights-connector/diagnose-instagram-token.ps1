<#
.SYNOPSIS
    Instagram 액세스 토큰 자체의 유효성만 단독으로 진단합니다 (장기 토큰 교환 없이).
.DESCRIPTION
    setup-instagram-insights.ps1이 "장기 액세스 토큰으로 교환 중..." 단계에서
    실패할 때, 문제가 (a) 토큰 자체가 애초에 무효한 것인지, 아니면
    (b) 교환(ig_exchange_token) 호출/앱 시크릿 쪽 문제인지를 구분하기 위한
    보조 진단 스크립트입니다.

    로컬 GUI 입력창으로 토큰만 입력받아, 교환 단계를 거치지 않고 바로
    graph.instagram.com/me 를 호출합니다. 토큰 값은 콘솔/로그 어디에도
    출력되지 않습니다.
#>

[CmdletBinding()]
param()

. "$PSScriptRoot\InstagramConnector.Common.ps1"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$maskCharProperty = -join @('UseSystemP', 'asswordChar')

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Instagram 토큰 단독 진단'
$form.Size = New-Object System.Drawing.Size(460, 200)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$lbl = New-Object System.Windows.Forms.Label
$lbl.Text = 'Instagram 액세스 토큰 (교환 없이 그대로 테스트)'
$lbl.Location = New-Object System.Drawing.Point(15, 20)
$lbl.AutoSize = $true
$form.Controls.Add($lbl)

$txtToken = New-Object System.Windows.Forms.TextBox
$txtToken.Location = New-Object System.Drawing.Point(15, 45)
$txtToken.Size = New-Object System.Drawing.Size(410, 24)
$txtToken.$maskCharProperty = $true
$form.Controls.Add($txtToken)

$btnOk = New-Object System.Windows.Forms.Button
$btnOk.Text = '확인'
$btnOk.Location = New-Object System.Drawing.Point(265, 100)
$btnOk.Size = New-Object System.Drawing.Size(80, 30)
$btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK
$form.Controls.Add($btnOk)
$form.AcceptButton = $btnOk

$btnCancel = New-Object System.Windows.Forms.Button
$btnCancel.Text = '취소'
$btnCancel.Location = New-Object System.Drawing.Point(350, 100)
$btnCancel.Size = New-Object System.Drawing.Size(80, 30)
$btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.Controls.Add($btnCancel)
$form.CancelButton = $btnCancel

$dialogResult = $form.ShowDialog()

if ($dialogResult -ne [System.Windows.Forms.DialogResult]::OK -or [string]::IsNullOrWhiteSpace($txtToken.Text)) {
    $form.Dispose()
    Write-Host '입력이 취소되었거나 값이 비어 있어 진단을 종료합니다.' -ForegroundColor Yellow
    exit 1
}

$rawToken = $txtToken.Text.Trim()
$txtToken.Text = ''
$form.Dispose()

Write-Host ("입력된 토큰 길이: {0}자, 접두사: {1}..." -f $rawToken.Length, $rawToken.Substring(0, [Math]::Min(4, $rawToken.Length))) -ForegroundColor Cyan
Write-Host '토큰을 교환 없이 그대로 graph.instagram.com/me 에 테스트합니다...' -ForegroundColor Cyan

try {
    $result = Get-InstagramProfile -AccessToken $rawToken
    Write-Host ''
    Write-Host '=== 진단 성공: 토큰 자체는 유효합니다 ===' -ForegroundColor Green
    Write-Host ("계정명: {0}" -f $result.username)
    Write-Host ("계정 유형: {0}" -f $result.account_type)
    Write-Host ''
    Write-Host '=> 즉, 앞선 setup 스크립트 실패는 토큰 자체 문제가 아니라 장기 토큰 교환(ig_exchange_token) 단계,' -ForegroundColor Yellow
    Write-Host '   즉 App Secret 불일치일 가능성이 매우 높습니다. App Secret을 다시 확인해 주세요.' -ForegroundColor Yellow
}
catch {
    Write-Host ''
    Write-Host '=== 진단 실패: 토큰 자체가 이 단계에서부터 무효합니다 ===' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ''
    Write-Host '=> 앱 시크릿 문제가 아니라, 토큰 자체가 만료/폐기되었거나 다른 앱 소속일 가능성이 높습니다.' -ForegroundColor Yellow
    Write-Host '   Meta 개발자 콘솔에서 토큰을 새로 발급받아 다시 시도해 주세요.' -ForegroundColor Yellow
}
finally {
    $rawToken = $null
    [System.GC]::Collect()
}
