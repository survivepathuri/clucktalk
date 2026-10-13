<#
.SYNOPSIS
  Checks a deployed CluckTalk cloud pilot from this PC. Prints PASS / FAIL / WARN lines and no secret.
.DESCRIPTION
  From outside: HTTPS reachable, certificate valid and not about to expire, health endpoint ok, missing and wrong
  token rejected (401), the failed-token rate limit answers 429, paths the farmer's page does not use answer 404, the MCP
  port and the Simulator port are NOT reachable from the internet.
  Over ssh: the right token is accepted (read on the server into memory only, never printed), the app comes back after a
  service restart (and after a reboot with -Reboot), a backup can be made and passes its restore test, the timer is on,
  and the farm file is not the example.
  Exit code 0 only when nothing failed.
.EXAMPLE
  .\deploy\cloud\verify.ps1 -ServerIp 203.0.113.10              (uses ~\.ssh\clucktalk-pilot-ed25519; -KeyPath overrides it)
#>
param(
    [Parameter(Mandatory = $true)][string]$ServerIp,
    [string]$KeyPath = (Join-Path $env:USERPROFILE '.ssh\clucktalk-pilot-ed25519'),   # default: the ed25519 key made for this server
    [string]$User = 'ubuntu',
    [switch]$Reboot,
    [switch]$SkipRateLimit
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($ServerIp -notmatch '^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$') { throw 'ServerIp must be an IPv4 address.' }
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) { throw "The SSH key file was not found: $KeyPath" }
$HostName = ($ServerIp -replace '\.', '-') + '.sslip.io'
$Base = "https://$HostName"
$sshOpts = @('-i', $KeyPath, '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=accept-new', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10')
$target = "$User@$ServerIp"

$script:Failed = 0
function Report([string]$Status, [string]$Name, [string]$Detail = '') {
    if ($Status -eq 'FAIL') { $script:Failed++ }
    $line = '{0,-5} {1}' -f $Status, $Name
    if ($Detail) { $line += "  ($Detail)" }
    Write-Host $line
}
function Get-Status([string]$Url, [hashtable]$Headers = @{}, [string]$Method = 'GET') {
    # The HTTP status code of an answer, whatever it is (4xx and 5xx included); 0 when there is no answer at all.
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -Headers $Headers -Method $Method -TimeoutSec 15
        return [pscustomobject]@{ Code = [int]$r.StatusCode; Body = $r.Content }
    } catch [System.Net.WebException] {
        if ($_.Exception.Response) { return [pscustomobject]@{ Code = [int]$_.Exception.Response.StatusCode; Body = '' } }
        return [pscustomobject]@{ Code = 0; Body = $_.Exception.Message }
    }
}
function Invoke-Remote([string]$Command) {
    $ErrorActionPreference = 'Continue'   # Windows PowerShell 5.1 turns ssh's stderr text into errors otherwise
    $out = & ssh.exe @sshOpts $target $Command 2>&1
    return [pscustomobject]@{ Code = $LASTEXITCODE; Out = ($out | Out-String).Trim() }
}
function Test-PortOpen([string]$Address, [int]$Port, [int]$Millis = 5000) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync($Address, $Port)
        return ($task.Wait($Millis) -and $client.Connected)
    } catch { return $false } finally { $client.Dispose() }
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host "Checking $Base"
# ---- 1. HTTPS, certificate -----------------------------------------------------------------------------------------
$health = Get-Status "$Base/healthz"
if ($health.Code -eq 200 -and $health.Body -match '"ok"') { Report PASS 'HTTPS reachable and health endpoint ok' }
else { Report FAIL 'HTTPS reachable and health endpoint ok' "status $($health.Code); a certificate error also shows here" }

try {
    $tcp = New-Object System.Net.Sockets.TcpClient($HostName, 443)
    $ssl = New-Object System.Net.Security.SslStream($tcp.GetStream(), $false)   # default validation: chain, name, expiry
    $ssl.AuthenticateAsClient($HostName)
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($ssl.RemoteCertificate)
    $days = [int]($cert.NotAfter - (Get-Date)).TotalDays
    $issuer = ($cert.Issuer -replace '^.*?CN=([^,]+).*$', '$1')
    if ($days -ge 14) { Report PASS 'Certificate valid for this hostname' "issuer $issuer, $days days left" }
    else { Report FAIL 'Certificate valid for this hostname' "only $days days left" }
    $ssl.Dispose(); $tcp.Dispose()
} catch { Report FAIL 'Certificate valid for this hostname' $_.Exception.Message }

# ---- 2. tokens -----------------------------------------------------------------------------------------------------
$r = Get-Status "$Base/api/pilot/ui"
if ($r.Code -eq 401) { Report PASS 'Missing token is rejected' 'HTTP 401' } else { Report FAIL 'Missing token is rejected' "HTTP $($r.Code)" }
$r = Get-Status "$Base/api/pilot/ui" @{ Authorization = 'Bearer this-is-a-wrong-token-for-the-check-only' }
if ($r.Code -eq 401) { Report PASS 'Wrong token is rejected' 'HTTP 401' } else { Report FAIL 'Wrong token is rejected' "HTTP $($r.Code)" }

# The right token: read on the server into this variable only; never printed, never written.
$tok = Invoke-Remote "sudo grep -m1 '^CLUCKTALK_SIMULATOR_TOKENS=' /etc/clucktalk/pilot.env | cut -d= -f2- | cut -d, -f1"
if ($tok.Code -eq 0 -and $tok.Out.Length -ge 24) {
    $r = Get-Status "$Base/api/pilot/ui" @{ Authorization = "Bearer $($tok.Out)" }
    if ($r.Code -eq 200) { Report PASS 'The farmer token is accepted' 'HTTP 200' } else { Report FAIL 'The farmer token is accepted' "HTTP $($r.Code)" }
} else { Report FAIL 'The farmer token is accepted' 'could not read the token over ssh (check the key and the user)' }
$tok = $null

# ---- 3. exposure ---------------------------------------------------------------------------------------------------
foreach ($p in '/desktop', '/sandbox', '/mcp', '/api/state', '/api/resource', '/.env', '/static/index.html') {
    $r = Get-Status "$Base$p"
    if ($r.Code -eq 404) { Report PASS "Not exposed: $p" 'HTTP 404' } else { Report FAIL "Not exposed: $p" "HTTP $($r.Code)" }
}
foreach ($port in 8765, 8766) {
    if (Test-PortOpen $ServerIp $port) { Report FAIL "Port $port is NOT reachable from outside" 'it answered' }
    else { Report PASS "Port $port is NOT reachable from outside" 'no connection' }
}
$plain = Get-Status "http://$HostName/healthz"
if ($plain.Code -in 200, 301, 302, 307, 308) { Report PASS 'Port 80 answers (certificate renewal and redirect to HTTPS)' "HTTP $($plain.Code)" }
else { Report FAIL 'Port 80 answers (certificate renewal and redirect to HTTPS)' "HTTP $($plain.Code)" }

# ---- 4. rate limit ---------------------------------------------------------------------------------------------------
if ($SkipRateLimit) { Report WARN 'Failed-token rate limit' 'skipped' }
else {
    $limited = $false
    for ($i = 0; $i -lt 30 -and -not $limited; $i++) {
        $r = Get-Status "$Base/api/pilot/ui" @{ Authorization = 'Bearer rate-limit-check-with-a-wrong-token-only' }
        if ($r.Code -eq 429) { $limited = $true }
    }
    if ($limited) { Report PASS 'Failed-token rate limit answers 429' 'the farmer token has its own, separate counter' }
    else { Report FAIL 'Failed-token rate limit answers 429' 'no 429 after 30 wrong tokens' }
}

# ---- 5. server side: restart, backup, timer, farm file ---------------------------------------------------------------------
function Wait-Healthy([int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        $h = Get-Status "$Base/healthz"
        if ($h.Code -eq 200) { return $true }
        Start-Sleep -Seconds 3
    }
    return $false
}
$x = Invoke-Remote 'sudo systemctl restart clucktalk-pilot.service'
if ($x.Code -ne 0) { Report FAIL 'App comes back after a service restart' 'systemctl restart failed' }
elseif (Wait-Healthy 60) { Report PASS 'App comes back after a service restart' 'healthy again' }
else { Report FAIL 'App comes back after a service restart' 'not healthy after 60 s' }

$x = Invoke-Remote 'sudo systemctl is-enabled clucktalk-pilot.service caddy.service clucktalk-backup.timer'
if ($x.Code -eq 0) { Report PASS 'Starts at boot: app, Caddy, backup timer' 'enabled' } else { Report FAIL 'Starts at boot: app, Caddy, backup timer' $x.Out.Replace("`n", ' ') }

$x = Invoke-Remote 'sudo systemctl start clucktalk-backup.service && sudo cat /var/backups/clucktalk-pilot/LAST_GOOD_BACKUP | head -1'
if ($x.Code -eq 0) { Report PASS 'A backup can be made and passes the restore test' "last good: $($x.Out)" } else { Report FAIL 'A backup can be made and passes the restore test' 'see: sudo journalctl -u clucktalk-backup -n 30' }

$x = Invoke-Remote 'sudo test -e /var/lib/clucktalk-pilot/FARM_FILE_IS_EXAMPLE'   # the folder is private to the app user
if ($x.Code -eq 0) { Report WARN "Farm file" 'still the EXAMPLE (fictional houses): put the farmer''s real houses in before sending the link' }
else { Report PASS 'Farm file is not the example' }

if ($Reboot) {
    $null = Invoke-Remote 'sudo systemctl reboot'
    Start-Sleep -Seconds 20
    if (Wait-Healthy 240) { Report PASS 'App comes back after a reboot' 'healthy again' } else { Report FAIL 'App comes back after a reboot' 'not healthy after 4 minutes' }
} else { Report WARN 'Reboot test' 'not run (add -Reboot to run it)' }

Write-Host ''
if ($script:Failed -eq 0) { Write-Host 'All checks passed (WARN lines are things to read, not failures).'; exit 0 }
Write-Host "$($script:Failed) check(s) FAILED."; exit 1
