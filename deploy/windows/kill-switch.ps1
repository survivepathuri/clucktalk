<#
.SYNOPSIS
  The kill switch: -Action pause creates the DISABLED file (every page and call answers 503 at once, no restart),
  -Action resume removes it, -Action status says which. The file is the one named by CLUCKTALK_DISABLED_FILE in pilot.env.
#>
param(
    [Parameter(Mandatory = $true)][ValidateSet('pause', 'resume', 'status')][string]$Action,
    [string]$PilotRoot = 'C:\clucktalk-pilot'
)
. (Join-Path $PSScriptRoot 'common.ps1')

$paths = Get-PilotPaths $PilotRoot
$values = Read-PilotEnv $paths.EnvFile
if (-not $values.Contains('CLUCKTALK_DISABLED_FILE') -or (Test-Placeholder $values['CLUCKTALK_DISABLED_FILE'])) {
    throw 'CLUCKTALK_DISABLED_FILE is not set in pilot.env.'
}
$file = $values['CLUCKTALK_DISABLED_FILE']
switch ($Action) {
    'pause' {
        New-Item -ItemType Directory -Force -Path (Split-Path $file) | Out-Null
        Set-Content -LiteralPath $file -Value 'paused' -Encoding ASCII
        Write-Host 'Paused: the pilot answers 503 to everything except the health check.'
    }
    'resume' {
        Remove-Item -LiteralPath $file -ErrorAction SilentlyContinue
        Write-Host 'Resumed: the kill-switch file is removed.'
    }
    'status' {
        if (Test-Path -LiteralPath $file) { Write-Host 'The kill switch is ON (paused).' }
        else { Write-Host 'The kill switch is off (running normally).' }
    }
}
