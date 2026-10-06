<#
.SYNOPSIS
  One screen: does the page answer, is the kill switch on, how old is the last good backup, and the anonymous
  usage totals (numbers only; no farmer data, no tokens).
#>
param([string]$PilotRoot = 'C:\clucktalk-pilot')
. (Join-Path $PSScriptRoot 'common.ps1')

$paths = Get-PilotPaths $PilotRoot
$values = Read-PilotEnv $paths.EnvFile
$pagePort = Get-PilotPort $values 'CLUCKTALK_SIMULATOR_PORT' 8766

$proc = Get-PilotProcess $paths.PidFile
if ($null -eq $proc) { Write-Host 'Process: not running (no process recorded by start-pilot.ps1).' }
else { Write-Host "Process: running ($($proc.Id))." }
Write-Host "Health on 127.0.0.1:${pagePort}: $(Test-PilotHealth $pagePort)"
if ($values.Contains('CLUCKTALK_DISABLED_FILE') -and (Test-Path -LiteralPath $values['CLUCKTALK_DISABLED_FILE'])) {
    Write-Host 'Kill switch: ON (paused).'
}
else { Write-Host 'Kill switch: off.' }

# The backup age, from the stamp the backup script writes only after a copy passed its integrity check.
$stampFile = Join-Path $paths.Backups 'LAST_GOOD_BACKUP'
if (-not (Test-Path -LiteralPath $stampFile)) { Write-Host 'WARNING: no backup stamp found (has the backup ever run?).' }
else {
    try {
        $made = [DateTimeOffset]::Parse((Get-Content -LiteralPath $stampFile -TotalCount 1).Trim())
        $hours = ([DateTimeOffset]::UtcNow - $made).TotalHours
        Write-Host ('Last good backup: {0:N1} hours ago' -f $hours)
        if ($hours -gt 26) { Write-Host 'WARNING: the last good backup is more than 26 hours old. Run backup-pilot.ps1 and check the scheduled task.' }
    }
    catch { Write-Host 'WARNING: the backup stamp is unreadable.' }
}

$usage = if ($values.Contains('CLUCKTALK_USAGE_PATH')) { $values['CLUCKTALK_USAGE_PATH'] } else { '' }
if ($usage -ne '' -and (Test-Path -LiteralPath $usage)) {
    Push-Location $script:RepoRoot
    try { & $script:VenvPython 'tasks.py' 'pilot-stats' '--usage' $usage } finally { Pop-Location }
}
else { Write-Host 'Usage: no usage file yet (nobody has confirmed a record).' }
