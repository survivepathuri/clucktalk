<#
.SYNOPSIS
  A consistent backup of the pilot's SQLite state, kept in C:\clucktalk-pilot\backups\ (the newest 14).
.DESCRIPTION
  Runs deploy\backup_sqlite.py, which uses Python's sqlite3 online backup API (safe while the server runs; never a
  plain file copy), checks the copy with PRAGMA integrity_check, keeps the newest 14, and writes the LAST_GOOD_BACKUP
  stamp only after a copy passed. Then it proves the newest backup can be restored (deploy\restore_test.py: row counts
  only, never a row). With -CopyTo (for example a USB drive such as E:\clucktalk-backup) it also copies the newest
  backup there. The backups hold the farmer's records: keep the folder and the drive private.
#>
param(
    [string]$PilotRoot = 'C:\clucktalk-pilot',
    [string]$CopyTo = '',
    [int]$Keep = 14
)
. (Join-Path $PSScriptRoot 'common.ps1')

$paths = Get-PilotPaths $PilotRoot
if (-not (Test-Path -LiteralPath $script:VenvPython)) { throw "The repository's virtual environment is missing. Run  python tasks.py setup  first." }
$values = Read-PilotEnv $paths.EnvFile
$state = $values['CLUCKTALK_STATE_PATH']
if (Test-Placeholder $state) { throw 'CLUCKTALK_STATE_PATH is not set in pilot.env.' }
if (-not (Test-Path -LiteralPath $state -PathType Leaf)) { throw "There is no state file yet at $state (has the pilot ever started?)." }
if ($Keep -lt 1) { throw '-Keep must be at least 1.' }

New-Item -ItemType Directory -Force -Path $paths.Backups | Out-Null
Restrict-ToCurrentUser $paths.Backups

$arguments = @('deploy\backup_sqlite.py', '--state', $state, '--dest', $paths.Backups, '--keep', "$Keep")
if ($values.Contains('CLUCKTALK_USAGE_PATH') -and (Test-Path -LiteralPath $values['CLUCKTALK_USAGE_PATH'])) {
    $arguments += @('--also', $values['CLUCKTALK_USAGE_PATH'])
}
Push-Location $script:RepoRoot
try {
    & $script:VenvPython @arguments
    if ($LASTEXITCODE -ne 0) { throw 'The backup FAILED. No new stamp was written.' }
    & $script:VenvPython 'deploy\restore_test.py' --dest $paths.Backups --live $state
    if ($LASTEXITCODE -ne 0) { throw 'The restore test FAILED: the newest backup cannot be restored.' }
}
finally { Pop-Location }

$stem = [System.IO.Path]::GetFileNameWithoutExtension($state)
$newest = Get-ChildItem -LiteralPath $paths.Backups -Filter "${stem}_*.sqlite3" | Sort-Object Name | Select-Object -Last 1
if ($CopyTo -ne '') {
    if (Test-InsideFolder $CopyTo $script:RepoRoot) { throw '-CopyTo must not be inside the repository.' }
    New-Item -ItemType Directory -Force -Path $CopyTo | Out-Null
    Copy-Item -LiteralPath $newest.FullName -Destination $CopyTo -Force
    $copied = Join-Path $CopyTo $newest.Name
    if (-not (Test-Path -LiteralPath $copied) -or (Get-Item $copied).Length -ne $newest.Length) { throw "The copy to $CopyTo did not match the backup." }
    Write-Host "Copied $($newest.Name) to $CopyTo (the drive now holds the farmer's records: keep it private)."
}
Write-Host "Backup done: $($newest.Name). Folder: $($paths.Backups) (the newest $Keep are kept)."
