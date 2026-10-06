<#
.SYNOPSIS
  Starts the pilot (the MCP server and the Simulator page) on 127.0.0.1 only, after strict checks.
.DESCRIPTION
  Reads pilot.env, refuses to start when a required variable is missing, a token is weak, the state file or the farm
  file lies inside the repository or is the demo's file, or the server would listen beyond this machine. The output and
  the log files hold no tokens and no farmer words (the app does not log them; this script prints names, never values).
#>
param([string]$PilotRoot = 'C:\clucktalk-pilot')
. (Join-Path $PSScriptRoot 'common.ps1')

function Stop-Refusing([string]$Message) {
    Write-Host "REFUSED: $Message"
    exit 1
}

$paths = Get-PilotPaths $PilotRoot
if (-not (Test-Path -LiteralPath $script:VenvPython)) {
    Stop-Refusing "the repository's virtual environment is missing. Run  python tasks.py setup  in the repository first."
}
try { $values = Read-PilotEnv $paths.EnvFile } catch { Stop-Refusing $_.Exception.Message }

# 1. Required variables must be present and must not be placeholders.
$required = 'CLUCKTALK_MODE', 'MOCK_BEDROCK', 'CLUCKTALK_PUBLIC_ORIGIN', 'CLUCKTALK_SIMULATOR_TOKENS',
    'CLUCKTALK_AUTH_TOKEN', 'CLUCKTALK_STATE_PATH', 'CLUCKTALK_PILOT_FARM_PATH'
foreach ($name in $required) {
    if (-not $values.Contains($name) -or (Test-Placeholder $values[$name])) {
        Stop-Refusing "the required variable $name is missing or still a placeholder in pilot.env."
    }
}
if ($values['CLUCKTALK_MODE'] -ne 'pilot') { Stop-Refusing 'CLUCKTALK_MODE must be pilot.' }
if ($values['MOCK_BEDROCK'] -ne 'true') { Stop-Refusing 'MOCK_BEDROCK must be true (the pilot has no live AI).' }
if ($values['CLUCKTALK_PUBLIC_ORIGIN'] -cnotmatch '^https://[a-z0-9][a-z0-9.-]*[a-z0-9]$') {
    Stop-Refusing 'CLUCKTALK_PUBLIC_ORIGIN must be an exact https address in lowercase with no path and no port.'
}

# 2. The MCP server must stay on this machine: a listening address or a demo clock must never be set.
foreach ($forbidden in 'CLUCKTALK_HOST', 'CLUCKTALK_DEMO_DAYS_LATER') {
    if ($values.Contains($forbidden)) { Stop-Refusing "$forbidden must not be set in pilot.env (the server must stay on 127.0.0.1)." }
}
$mcpPort = Get-PilotPort $values 'CLUCKTALK_PORT' 8765
$pagePort = Get-PilotPort $values 'CLUCKTALK_SIMULATOR_PORT' 8766
if ($mcpPort -eq $pagePort) { Stop-Refusing 'the MCP port and the page port must be different.' }

# 3. Weak tokens are refused: 32 to 128 allowed characters, at least 12 different ones, no obvious words, all different.
function Test-WeakToken([string]$Token) {
    if ($Token -cnotmatch '^[A-Za-z0-9._~-]{32,128}$') { return $true }
    if (($Token.ToCharArray() | Select-Object -Unique).Count -lt 12) { return $true }
    if ($Token -match '(?i)password|changeme|example|secret|token|clucktalk|pilot|123456|qwerty') { return $true }
    return $false
}
$farmerTokens = @($values['CLUCKTALK_SIMULATOR_TOKENS'] -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
$all = @($farmerTokens) + @($values['CLUCKTALK_AUTH_TOKEN'])
foreach ($t in $all) {
    if (Test-WeakToken $t) { Stop-Refusing 'a token is weak (too short, too repetitive or guessable). Make strong ones with new-token.ps1.' }
}
if (@($all | Select-Object -Unique).Count -ne $all.Count) { Stop-Refusing 'every token must be different (the MCP token and each farmer token).' }

# 4. The data files: absolute, outside the repository, never the demo's file; the farm file must exist.
$demoState = Join-Path $script:RepoRoot '.local\clucktalk.sqlite3'
$dataVars = 'CLUCKTALK_STATE_PATH', 'CLUCKTALK_PILOT_FARM_PATH', 'CLUCKTALK_DAILY_DEATHS_RULE_PATH', 'CLUCKTALK_USAGE_PATH',
    'CLUCKTALK_DISABLED_FILE', 'CLUCKTALK_WEATHER_RULES_PATH'
foreach ($name in $dataVars) {
    if (-not $values.Contains($name) -or $values[$name] -eq '') { continue }
    $p = $values[$name]
    if (-not [System.IO.Path]::IsPathRooted($p)) { Stop-Refusing "$name must be an absolute path." }
    if (Test-InsideFolder $p $script:RepoRoot) { Stop-Refusing "$name is inside the repository; real farm data must live outside it." }
    if ([System.IO.Path]::GetFullPath($p) -ieq [System.IO.Path]::GetFullPath($demoState)) { Stop-Refusing "$name is the demo's state file." }
}
$state = $values['CLUCKTALK_STATE_PATH']
$farm = $values['CLUCKTALK_PILOT_FARM_PATH']
if ((Split-Path -Leaf $farm) -match '(?i)example') { Stop-Refusing 'the farm file looks like the example file; use the real farm file.' }
if (-not (Test-Path -LiteralPath $farm -PathType Leaf)) { Stop-Refusing "the farm file does not exist: $farm" }
if ($state -cnotmatch '(?i)pilot[^\\]*\.sqlite3$') { Stop-Refusing 'the state file must be a .sqlite3 file whose name contains pilot.' }

# 5. Not twice.
if (Get-PilotProcess $paths.PidFile) { Stop-Refusing 'the pilot already runs (use stop-pilot.ps1 first).' }

# Start: only the values of pilot.env reach the process (stray CLUCKTALK_* settings of this shell are removed first).
Get-ChildItem Env: | Where-Object { $_.Name -like 'CLUCKTALK_*' -or $_.Name -eq 'MOCK_BEDROCK' } | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
foreach ($name in $values.Keys) { Set-Item -LiteralPath "Env:$name" -Value $values[$name] }
New-Item -ItemType Directory -Force -Path $paths.Logs, (Split-Path $state) | Out-Null
$out = Join-Path $paths.Logs 'pilot.out.log'
$err = Join-Path $paths.Logs 'pilot.err.log'
foreach ($f in $out, $err) {
    if ((Test-Path $f) -and ((Get-Item $f).Length -gt 5MB)) { Move-Item -Force $f "$f.old" }
}
$proc = Start-Process -FilePath $script:VenvPython -ArgumentList 'scripts\run_instance.py' -WorkingDirectory $script:RepoRoot `
    -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
Set-Content -LiteralPath $paths.PidFile -Value $proc.Id -Encoding ASCII

# Wait for the page's health endpoint (up to 30 seconds).
$health = 'no answer'
for ($i = 0; $i -lt 30 -and $health -eq 'no answer'; $i++) {
    Start-Sleep -Seconds 1
    if ($proc.HasExited) { break }
    $health = Test-PilotHealth $pagePort
}
if ($proc.HasExited) {
    Remove-Item -LiteralPath $paths.PidFile -ErrorAction SilentlyContinue
    Write-Host "The pilot stopped at once. Read the last lines of $err (they hold no tokens)."
    exit 1
}
Write-Host "Pilot started (process $($proc.Id)). Health on 127.0.0.1:$pagePort : $health"
Write-Host "Forward the tunnel to port $pagePort ONLY. Logs: $out and $err"
if ($health -ne 'ok') { Write-Host 'The page did not answer ok yet. Run status-pilot.ps1 in a moment.' }
