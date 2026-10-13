<#
.SYNOPSIS
  Asks a few questions and writes the farmer's pilot farm file, checked by the same parser the app uses.
.DESCRIPTION
  Run it at the farm with the Telugu question sheet (docs/FARMER_QUESTIONS_TE.md). Per shed it asks: birds placed,
  placement date, birds that died so far, feed stock. It never asks for or stores a name, phone number or address.
  The four other required values (feed price, its label, the simulated live-bird price, supplier lead days) are
  copied from docs/pilot_farm.example.json: they are PLACEHOLDERS, not the farmer's own numbers.
  The file is checked with clucktalk.pilot.parse_pilot_farm / build_pilot_farm (the project's venv python) and is not
  written if that fails. The default output is .local\real_pilot_farm.json, which git ignores; the script refuses any
  other path that git does not ignore. Nothing is uploaded: afterwards run deploy.ps1 -FarmFile <that path>.
.EXAMPLE
  .\deploy\cloud\make-farm.ps1
  .\deploy\cloud\make-farm.ps1 -Out .local\real_pilot_farm.json
#>
param(
    [string]$Out = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Example = Join-Path $RepoRoot 'docs\pilot_farm.example.json'
if ($Out -eq '') { $Out = Join-Path $RepoRoot '.local\real_pilot_farm.json' }
elseif (-not [System.IO.Path]::IsPathRooted($Out)) { $Out = Join-Path (Get-Location).Path $Out }

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'The project venv was not found. Run: python tasks.py setup' }
if (-not (Test-Path -LiteralPath $Example -PathType Leaf)) { throw 'docs\pilot_farm.example.json was not found.' }

# ---- the output path must be ignored by git, or we stop (the file holds the farmer's real numbers) ---------------
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Out) | Out-Null
& git -C $RepoRoot check-ignore -q -- $Out
if ($LASTEXITCODE -ne 0) { throw "STOP: git does not ignore $Out. Choose a path under .local\ (ignored) and run again." }

# ---- "today" is the farmer's today (India), as in the app ------------------------------------------------------
try { $tz = [TimeZoneInfo]::FindSystemTimeZoneById('India Standard Time') } catch { $tz = [TimeZoneInfo]::FindSystemTimeZoneById('Asia/Kolkata') }
$today = [TimeZoneInfo]::ConvertTime([DateTime]::UtcNow, $tz).Date

function Ask-Int([string]$Prompt, [int]$Low, [int]$High, $Default = $null) {
    while ($true) {
        $suffix = if ($null -ne $Default) { " [$Default]" } else { '' }
        $raw = (Read-Host "$Prompt ($Low-$High)$suffix").Trim()
        if ($raw -eq '' -and $null -ne $Default) { return [int]$Default }
        $n = 0
        if ($raw -match '^\d{1,9}$' -and [int]::TryParse($raw, [ref]$n) -and $n -ge $Low -and $n -le $High) { return $n }
        Write-Host "  Please type a whole number from $Low to $High."
    }
}
function Ask-Date([string]$Prompt) {
    while ($true) {
        $raw = (Read-Host "$Prompt (YYYY-MM-DD)").Trim()
        $d = [DateTime]::MinValue
        if (-not [DateTime]::TryParseExact($raw, 'yyyy-MM-dd', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None, [ref]$d)) {
            Write-Host '  Please type the date like 2026-10-01.'; continue
        }
        if ($d.Date -gt $today) { Write-Host "  That date is in the future (today is $($today.ToString('yyyy-MM-dd')))."; continue }
        $age = ($today - $d.Date).Days
        if ($age -gt 120) {
            $ok = (Read-Host "  WARNING: that is $age days ago (more than 120). Is it right? (yes/no)").Trim().ToLower()
            if ($ok -ne 'yes') { continue }
        }
        return $d.Date
    }
}
function Ask-Decimal([string]$Prompt, [double]$High, $Default) {
    while ($true) {
        $raw = (Read-Host "$Prompt (0-$High) [$Default]").Trim()
        if ($raw -eq '') { return [double]$Default }
        $n = 0.0
        if ($raw -match '^\d{1,7}(\.\d{1,2})?$' -and [double]::TryParse($raw, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$n) -and $n -ge 0 -and $n -le $High) { return $n }
        Write-Host "  Please type a number from 0 to $High."
    }
}

# ---- placeholders from the example file -------------------------------------------------------------------------
$ex = Get-Content -LiteralPath $Example -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host ''
Write-Host 'Farm questions. Do NOT ask for or type a name, phone number, Aadhaar or address.'
Write-Host "Today (India): $($today.ToString('yyyy-MM-dd'))"
Write-Host ''

$sheds = Ask-Int 'How many sheds' 1 6
$houses = @()
for ($i = 1; $i -le $sheds; $i++) {
    Write-Host ''
    Write-Host "--- Shed $i ---"
    $birds = Ask-Int "Shed ${i}: birds placed" 1 100000
    $placed = Ask-Date "Shed ${i}: placement date"
    $deaths = Ask-Int "Shed ${i}: birds that died so far" 0 $birds 0
    $stock = Ask-Decimal "Shed ${i}: feed stock in kg" 100000 0
    $houses += [ordered]@{
        number = $i; birds_placed = $birds; placed_on = $placed.ToString('yyyy-MM-dd')
        deaths_before_pilot = $deaths; feed_stock_kg = $stock
    }
}

$farm = [ordered]@{
    feed_price_per_kg_inr                = [string]$ex.feed_price_per_kg_inr
    feed_price_label                     = [string]$ex.feed_price_label
    simulated_live_bird_price_per_kg_inr = [string]$ex.simulated_live_bird_price_per_kg_inr
    supplier_lead_days                   = [int]$ex.supplier_lead_days
    houses                               = $houses
}
$json = $farm | ConvertTo-Json -Depth 5

# ---- check with the app's own parser BEFORE anything is written -------------------------------------------------
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('clucktalk-farm-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
$stage = Join-Path $tmp 'farm.json'
$checker = Join-Path $tmp 'check_farm.py'
$check = @'
import json, sys
from datetime import date
sys.path.insert(0, sys.argv[3])
from clucktalk.pilot import PilotFarmError, build_pilot_farm, parse_pilot_farm
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        config = parse_pilot_farm(json.load(f))
    build_pilot_farm(config, date.fromisoformat(sys.argv[2]))
except PilotFarmError as exc:
    print(f"REFUSED by the app's farm parser: {exc}")
    raise SystemExit(1)
print("ok")
'@
try {
    [System.IO.File]::WriteAllText($stage, $json, (New-Object System.Text.UTF8Encoding($false)))
    [System.IO.File]::WriteAllText($checker, $check, (New-Object System.Text.UTF8Encoding($false)))
    $result = & $Python -I $checker $stage $today.ToString('yyyy-MM-dd') (Join-Path $RepoRoot 'src')
    if ($LASTEXITCODE -ne 0) { Write-Host $result; throw 'Not written: the farm did not pass the app''s own check. Run the script again with corrected answers.' }
} finally {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

# ---- read-back, then yes/no ---------------------------------------------------------------------------------------
Write-Host ''
Write-Host 'Read back (checked by the app''s parser: OK):'
foreach ($h in $houses) {
    $age = ($today - [DateTime]::ParseExact($h.placed_on, 'yyyy-MM-dd', [Globalization.CultureInfo]::InvariantCulture)).Days
    Write-Host ("  Shed {0}: {1} birds placed on {2} ({3} days old), {4} died so far, feed stock {5} kg" -f $h.number, $h.birds_placed, $h.placed_on, $age, $h.deaths_before_pilot, $h.feed_stock_kg)
}
Write-Host ''
Write-Host 'NOTE: these four values are PLACEHOLDERS copied from docs\pilot_farm.example.json, NOT the farmer''s own numbers:'
Write-Host ("  feed price {0} INR/kg, live-bird price {1} INR/kg (Simulated), supplier lead {2} days, label: {3}" -f $farm.feed_price_per_kg_inr, $farm.simulated_live_bird_price_per_kg_inr, $farm.supplier_lead_days, $farm.feed_price_label)
Write-Host '  Feed-cost and sale-plan answers use them, so do not present those numbers to the farmer as his.'
Write-Host ''
$answer = (Read-Host "Save to $Out ? (yes/no)").Trim().ToLower()
if ($answer -ne 'yes') { Write-Host 'Nothing was written.'; return }
if (Test-Path -LiteralPath $Out) {
    $over = (Read-Host 'That file already exists. Overwrite it? (yes/no)').Trim().ToLower()
    if ($over -ne 'yes') { Write-Host 'Nothing was written.'; return }
}
[System.IO.File]::WriteAllText($Out, $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Host ''
Write-Host "Written: $Out  (git ignores it; never commit or paste it)"
Write-Host "Next: .\deploy\cloud\deploy.ps1 -ServerIp <IP> -FarmFile `"$Out`"   (see docs\CLOUD_PILOT.md, 'Switching from the sample farm to the real one')"
