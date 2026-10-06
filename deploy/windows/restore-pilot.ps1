<#
.SYNOPSIS
  Restores the pilot's state file from a backup. The pilot must be stopped first.
.DESCRIPTION
  Checks the backup first (deploy\restore_test.py), moves the damaged state file ASIDE (never deletes it), also moves
  aside any -journal, -wal or -shm file lying beside it (they belong to the old file and can undo or corrupt the
  restored one), then copies the backup into place. It does not start the pilot.
#>
param(
    [Parameter(Mandatory = $true)][string]$BackupFile,
    [string]$PilotRoot = 'C:\clucktalk-pilot',
    [switch]$Yes
)
. (Join-Path $PSScriptRoot 'common.ps1')

$paths = Get-PilotPaths $PilotRoot
$values = Read-PilotEnv $paths.EnvFile
$state = $values['CLUCKTALK_STATE_PATH']
if (Test-Placeholder $state) { throw 'CLUCKTALK_STATE_PATH is not set in pilot.env.' }
if (-not (Test-Path -LiteralPath $BackupFile -PathType Leaf)) { throw "No such backup file: $BackupFile" }
if (-not (Test-Path -LiteralPath $script:VenvPython)) { throw "The repository's virtual environment is missing. Run  python tasks.py setup  first." }

if (Get-PilotProcess $paths.PidFile) { throw 'The pilot is running. Run stop-pilot.ps1 first.' }
$pagePort = Get-PilotPort $values 'CLUCKTALK_SIMULATOR_PORT' 8766
if ((Test-PilotHealth $pagePort) -ne 'no answer') { throw "Something still answers on port $pagePort. Stop the pilot first." }

Push-Location $script:RepoRoot
try {
    & $script:VenvPython 'deploy\restore_test.py' --backup $BackupFile
    if ($LASTEXITCODE -ne 0) { throw 'That backup did not pass the restore test. Nothing was changed.' }
}
finally { Pop-Location }

if (-not $Yes) {
    $answer = Read-Host "Replace the live state file with this backup? The current file is kept aside. Type RESTORE to continue"
    if ($answer -cne 'RESTORE') { Write-Host 'Cancelled. Nothing was changed.'; exit 1 }
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
foreach ($suffix in '', '-journal', '-wal', '-shm') {
    $file = "$state$suffix"
    if (Test-Path -LiteralPath $file) {
        Move-Item -LiteralPath $file -Destination "$file.aside-$stamp"
        Write-Host "Moved aside: $(Split-Path -Leaf $file) -> $(Split-Path -Leaf $file).aside-$stamp"
    }
}
New-Item -ItemType Directory -Force -Path (Split-Path $state) | Out-Null
Copy-Item -LiteralPath $BackupFile -Destination $state
Write-Host 'Restored. Start the pilot with start-pilot.ps1, then run status-pilot.ps1.'
Write-Host 'The old files kept aside hold the farmer''s records too: delete them when they are no longer needed.'
