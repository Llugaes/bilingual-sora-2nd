# Maintainer-only relay. Never shipped in, or started by, the player application.
[CmdletBinding()]
param(
    [ValidateSet('Setup', 'Install', 'Run', 'Status', 'Remove')]
    [string]$Mode = 'Status',
    [Security.SecureString]$Token,
    [ValidatePattern('^v?\d+\.\d+\.\d+$')]
    [string]$Tag,
    [switch]$WaitForRelease
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$relayDirectory = Join-Path $projectRoot '.local\gitee-relay'
$credentialPath = Join-Path $relayDirectory 'publisher.credential.xml'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$taskName = 'Sora Bilingual - Gitee Release Relay'
$repository = 'Llugaes/bilingual-sora-2nd'

if ($WaitForRelease -and ($Mode -ne 'Run' -or -not $Tag)) {
    throw 'WaitForRelease requires -Mode Run and an explicit -Tag.'
}

function Remove-LegacyTask {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $task) { return }
    if ($task.Actions.Count -ne 1 -or $task.Actions.WorkingDirectory -ne $projectRoot) {
        throw 'Existing task belongs to another checkout; refusing to change it.'
    }
    Disable-ScheduledTask -TaskName $taskName | Out-Null
    if ($task.State -eq 'Running' -or (Get-ScheduledTask -TaskName $taskName).State -eq 'Running') {
        throw 'Legacy relay is still running; let it finish, then run Setup again.'
    }
    # Migration only: remove old triggers without touching the credential/cache.
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

if ($Mode -eq 'Status') {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    $receiptPath = Join-Path $relayDirectory 'verified.json'
    $lastTag = if (Test-Path -LiteralPath $receiptPath) {
        (Get-Content -Raw -LiteralPath $receiptPath | ConvertFrom-Json).source.tag
    } else { 'None' }
    [PSCustomObject]@{
        Execution = 'On demand only'
        CredentialConfigured = Test-Path -LiteralPath $credentialPath
        LastVerifiedTag = $lastTag
        LegacyScheduledTask = if ($task) { $task.State } else { 'Absent' }
        Log = Join-Path $relayDirectory 'relay.log'
    }
    exit 0
}

if ($Mode -eq 'Remove') {
    Remove-LegacyTask
    if (Test-Path -LiteralPath $credentialPath) { Remove-Item -LiteralPath $credentialPath }
    Write-Output 'Local publishing credential removed; download cache retained.'
    exit 0
}

if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create the development .venv first.' }
New-Item -ItemType Directory -Path $relayDirectory -Force | Out-Null

# Install remains an alias for older commands, but never registers a task.
Remove-LegacyTask
if ($Mode -in @('Setup', 'Install')) {
    if (-not $Token -and -not (Test-Path -LiteralPath $credentialPath)) {
        $Token = Read-Host 'Gitee repository-scoped release token (hidden)' -AsSecureString
    }
    if ($Token) {
        if ($Token.Length -eq 0) { throw 'The release token cannot be empty.' }
        # Windows DPAPI binds the encrypted credential to this user on this PC.
        [Management.Automation.PSCredential]::new('gitee-release', $Token) |
            Export-Clixml -LiteralPath $credentialPath
    }
    Write-Output 'Credential ready. Run explicitly after a GitHub release; no scheduled task or background listener.'
    exit 0
}

if (-not (Test-Path -LiteralPath $credentialPath)) { throw 'No local publishing credential; run Setup first.' }
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
        $relayArguments = @('-X', 'utf8', '-m', 'tools.relay_gitee', '--repository', $repository, '--directory', $relayDirectory)
        if ($Tag) { $relayArguments += @('--tag', $Tag) }
        if ($WaitForRelease) { $relayArguments += '--wait-for-release' }
        & $pythonPath @relayArguments 2>&1 | ForEach-Object {
            $_ | Out-File -FilePath $logPath -Append -Encoding utf8
            Write-Output $_
        }
        $exitCode = $LASTEXITCODE
    } finally { Pop-Location }
    Add-Content -LiteralPath $logPath -Encoding utf8 -Value "$((Get-Date).ToString('o')) Relay exit code: $exitCode"
} finally {
    $env:GITEE_RELEASE_TOKEN = $previousToken
    $credential = $null
}
exit $exitCode
