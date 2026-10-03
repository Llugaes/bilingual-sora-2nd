# Maintainer-only relay. Never shipped in, or started by, the player application.
[CmdletBinding()]
param(
    [ValidateSet('Install', 'Run', 'Status', 'Remove')]
    [string]$Mode = 'Status',
    [Security.SecureString]$Token
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$relayDirectory = Join-Path $projectRoot '.local\gitee-relay'
$credentialPath = Join-Path $relayDirectory 'publisher.credential.xml'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$taskName = 'Sora Bilingual - Gitee Release Relay'
$repository = 'Llugaes/bilingual-sora-2nd'
$scriptPath = $PSCommandPath

if ($Mode -eq 'Status') {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        $task | Select-Object TaskName, State
        Get-ScheduledTaskInfo -TaskName $taskName |
            Select-Object LastRunTime, LastTaskResult, NextRunTime
    } else { Write-Output 'Local release relay is not installed.' }
    exit 0
}

if ($Mode -eq 'Remove') {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        if ($task.Actions.WorkingDirectory -ne $projectRoot) {
            throw 'Existing task belongs to another checkout; refusing to change it.'
        }
        Stop-ScheduledTask -TaskName $taskName
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
    if (Test-Path -LiteralPath $credentialPath) { Remove-Item -LiteralPath $credentialPath }
    Write-Output 'Relay task and local publishing credential removed; download cache retained.'
    exit 0
}

if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create the development .venv first.' }
New-Item -ItemType Directory -Path $relayDirectory -Force | Out-Null

if ($Mode -eq 'Install') {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing -and $existing.Actions.WorkingDirectory -ne $projectRoot) {
        throw 'Existing task belongs to another checkout; refusing to replace it.'
    }
    if (-not $Token -and -not (Test-Path -LiteralPath $credentialPath)) {
        $Token = Read-Host 'Gitee repository-scoped release token (hidden)' -AsSecureString
    }
    if ($Token) {
        if ($Token.Length -eq 0) { throw 'The release token cannot be empty.' }
        # Windows DPAPI binds the encrypted credential to this user on this PC.
        [Management.Automation.PSCredential]::new('gitee-release', $Token) |
            Export-Clixml -LiteralPath $credentialPath
    }
    $action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
        -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -File `"$scriptPath`" -Mode Run" `
        -WorkingDirectory $projectRoot
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
    $triggers = @(
        (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)),
        (New-ScheduledTaskTrigger -AtLogOn -User $identity)
    )
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 45)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers `
        -Principal $principal -Settings $settings `
        -Description 'Relay verified original GitHub stable release files to Gitee; no builds or game access.' `
        -Force | Out-Null
    Write-Output 'Installed for the current user: every 15 minutes and at sign-in; no administrator service.'
    exit 0
}

if (-not (Test-Path -LiteralPath $credentialPath)) { throw 'No local publishing credential; run Install first.' }
$logPath = Join-Path $relayDirectory 'relay.log'
if ((Test-Path -LiteralPath $logPath) -and (Get-Item -LiteralPath $logPath).Length -gt 1MB) {
    Move-Item -LiteralPath $logPath -Destination "$logPath.previous" -Force
}
$previousToken = $env:GITEE_RELEASE_TOKEN
$exitCode = 1
try {
    $credential = Import-Clixml -LiteralPath $credentialPath
    $env:GITEE_RELEASE_TOKEN = $credential.GetNetworkCredential().Password
    Add-Content -LiteralPath $logPath -Encoding utf8 -Value "`n$((Get-Date).ToString('o')) Relay started"
    Push-Location $projectRoot
    try {
        [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
        & $pythonPath -X utf8 -m tools.relay_gitee --repository $repository --directory $relayDirectory 2>&1 |
            Out-File -FilePath $logPath -Append -Encoding utf8
        $exitCode = $LASTEXITCODE
    } finally { Pop-Location }
    Add-Content -LiteralPath $logPath -Encoding utf8 -Value "$((Get-Date).ToString('o')) Relay exit code: $exitCode"
} finally {
    $env:GITEE_RELEASE_TOKEN = $previousToken
    $credential = $null
}
exit $exitCode
