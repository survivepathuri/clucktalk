# Shared helpers for the Windows pilot scripts (dot-sourced by the other scripts). No secrets are ever printed here.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:VenvPython = Join-Path $script:RepoRoot '.venv\Scripts\python.exe'

function Get-PilotPaths([string]$PilotRoot) {
    [pscustomobject]@{
        Root    = $PilotRoot
        EnvFile = Join-Path $PilotRoot 'env\pilot.env'
        Logs    = Join-Path $PilotRoot 'logs'
        Backups = Join-Path $PilotRoot 'backups'
        PidFile = Join-Path $PilotRoot 'logs\pilot.pid'
    }
}

function Read-PilotEnv([string]$Path) {
    # KEY=VALUE lines; blank lines and # comments are skipped. Returns an ordered hashtable.
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "The environment file was not found: $Path" }
    $values = [ordered]@{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $text = $line.Trim()
        if ($text -eq '' -or $text.StartsWith('#')) { continue }
        $eq = $text.IndexOf('=')
        if ($eq -lt 1) { throw "A line in the environment file is not KEY=VALUE (line text is not shown)." }
        $values[$text.Substring(0, $eq).Trim()] = $text.Substring($eq + 1).Trim()
    }
    return $values
}

function Test-InsideFolder([string]$Path, [string]$Folder) {
    $p = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $f = [System.IO.Path]::GetFullPath($Folder).TrimEnd('\')
    return ($p -ieq $f) -or $p.StartsWith($f + '\', [System.StringComparison]::OrdinalIgnoreCase)
}

function Test-Placeholder([string]$Value) {
    return ($Value -eq '') -or ($Value -match '<[A-Za-z_ -]+>')
}

function Get-PilotPort($EnvValues, [string]$Name, [int]$Default) {
    if ($EnvValues.Contains($Name) -and $EnvValues[$Name] -ne '') { return [int]$EnvValues[$Name] }
    return $Default
}

function Get-PilotProcess([string]$PidFile) {
    # The launcher process recorded by start-pilot.ps1, or $null when it is not running.
    if (-not (Test-Path -LiteralPath $PidFile)) { return $null }
    $text = (Get-Content -LiteralPath $PidFile -TotalCount 1).Trim()
    if ($text -notmatch '^[0-9]+$') { return $null }
    return Get-Process -Id ([int]$text) -ErrorAction SilentlyContinue
}

function Test-PilotHealth([int]$Port) {
    # The health endpoint carries no data and needs no token. Returns 'ok', 'not ok' (kill switch) or 'no answer'.
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 5
        if ($r.Content -match '"ok"') { return 'ok' }
        return 'not ok'
    } catch [System.Net.WebException] {
        if ($_.Exception.Response -ne $null -and [int]$_.Exception.Response.StatusCode -eq 503) { return 'not ok' }
        return 'no answer'
    }
}

function Restrict-ToCurrentUser([string]$Path) {
    # Remove inherited permissions and leave only the current user. Output is hidden: it names accounts, not secrets.
    $me = "$env:USERDOMAIN\$env:USERNAME"
    & icacls.exe $Path /inheritance:r /grant:r "${me}:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not restrict the permissions of $Path to the current user." }
}
