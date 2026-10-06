<#
.SYNOPSIS
  Stops the pilot (the launcher and the two server processes it started).
#>
param([string]$PilotRoot = 'C:\clucktalk-pilot')
. (Join-Path $PSScriptRoot 'common.ps1')

$paths = Get-PilotPaths $PilotRoot
$proc = Get-PilotProcess $paths.PidFile
if ($null -eq $proc) {
    Write-Host 'The pilot is not running (no process recorded).'
    Remove-Item -LiteralPath $paths.PidFile -ErrorAction SilentlyContinue
    exit 0
}
# /T also ends the two child processes; the launcher cannot catch a Windows termination signal.
& taskkill.exe /PID $proc.Id /T /F | Out-Null
Start-Sleep -Seconds 1
Remove-Item -LiteralPath $paths.PidFile -ErrorAction SilentlyContinue
if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) {
    Write-Host 'The pilot did not stop. Close it in Task Manager.'
    exit 1
}
Write-Host 'The pilot is stopped. (The tunnel, if any, is separate: see the runbook.)'
