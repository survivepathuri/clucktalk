<#
.SYNOPSIS
  Runs  tasks.py pilot-stats  against the cloud pilot's data, over ssh. No public endpoint, no data leaves the server
  except the printed totals.
.DESCRIPTION
  Prints the same anonymous numbers as the PC pilot (days used, records confirmed, alerts by level, confirmed versus
  cancelled) and the age of the last good backup. The usage file holds counts only: no names, dates, words, sheds or tokens.
.EXAMPLE
  .\deploy\cloud\pilot-stats.ps1 -ServerIp 203.0.113.10         (uses ~\.ssh\clucktalk-pilot-ed25519; -KeyPath overrides it)
#>
param(
    [Parameter(Mandatory = $true)][string]$ServerIp,
    [string]$KeyPath = (Join-Path $env:USERPROFILE '.ssh\clucktalk-pilot-ed25519'),   # default: the ed25519 key made for this server
    [string]$User = 'ubuntu'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($ServerIp -notmatch '^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$') { throw 'ServerIp must be an IPv4 address.' }
if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) { throw "The SSH key file was not found: $KeyPath" }
$remote = 'sudo -u clucktalk-pilot env PYTHONDONTWRITEBYTECODE=1 /opt/clucktalk/.venv/bin/python /opt/clucktalk/tasks.py pilot-stats --usage /var/lib/clucktalk-pilot/state/usage_pilot.json --backups /var/backups/clucktalk-pilot'
& ssh.exe -i $KeyPath -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o BatchMode=yes "$User@$ServerIp" $remote
exit $LASTEXITCODE
