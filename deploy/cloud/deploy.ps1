<#
.SYNOPSIS
  Builds an allow-listed bundle of CluckTalk, uploads it to the cloud server and runs bootstrap.sh there.
.DESCRIPTION
  Runs on the Windows PC with the built-in OpenSSH (ssh.exe, scp.exe) and tar.exe. Only the files named in the
  allow-list below are shipped; nothing else in the repository can reach the server. The HTTPS hostname is built from the
  static IP: 203.0.113.10 -> 203-0-113-10.sslip.io (a free public DNS name that Caddy gets a Let's Encrypt certificate for).
  The script prints no token. Tokens are created on the server by bootstrap.sh; read the farmer link there (the last
  line printed says how).
  -DryRun (alias -WhatIf) builds and checks the bundle, lists its files and stops: no connection is made.
.EXAMPLE
  .\deploy\cloud\deploy.ps1 -ServerIp 203.0.113.10          (uses ~\.ssh\clucktalk-pilot-ed25519; -KeyPath overrides it)
  .\deploy\cloud\deploy.ps1 -ServerIp 203.0.113.10 -DryRun
#>
param(
    [Parameter(Mandatory = $true)][string]$ServerIp,
    [string]$KeyPath = (Join-Path $env:USERPROFILE '.ssh\clucktalk-pilot-ed25519'),   # default: the ed25519 key made for this server
    [string]$User = 'ubuntu',
    [string]$FarmFile = '',
    [string]$BundleOut = '',   # optional: also save the built bundle here (for inspection or tests)
    [Alias('WhatIf')][switch]$DryRun
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
# Windows' own tar (bsdtar). A GNU tar earlier on PATH (Git Bash) cannot write to a C:\ path.
$Tar = Join-Path $env:SystemRoot 'System32\tar.exe'
if (-not (Test-Path -LiteralPath $Tar)) { $Tar = 'tar.exe' }

# ---- inputs -------------------------------------------------------------------------------------------------
if ($ServerIp -notmatch '^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$') {
    throw 'ServerIp must be an IPv4 address such as 203.0.113.10 (use the Lightsail static IP).'
}
if ($User -notmatch '^[a-z_][a-z0-9_-]{0,31}$') { throw 'User must be a plain login name (Lightsail Ubuntu: ubuntu).' }
$HostName = ($ServerIp -replace '\.', '-') + '.sslip.io'
if (-not $DryRun) {
    if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) { throw "The SSH key file was not found: $KeyPath" }
    foreach ($tool in 'ssh.exe', 'scp.exe', $Tar) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool was not found (Windows 10/11 optional feature: OpenSSH Client)." }
    }
}
if ($FarmFile -ne '') {
    if (-not (Test-Path -LiteralPath $FarmFile -PathType Leaf)) { throw "The farm file was not found: $FarmFile" }
    try { $null = Get-Content -LiteralPath $FarmFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { throw 'The farm file is not valid JSON.' }
}

# ---- the allow-list: only these paths are ever shipped ------------------------------------------------------
$Files = @(
    'requirements.txt', 'pyproject.toml', 'LICENSE', 'NOTICE', 'tasks.py',
    'scripts/run_instance.py',
    'deploy/backup_sqlite.py', 'deploy/restore_test.py',
    'docs/pilot_farm.example.json',
    'deploy/cloud/bootstrap.sh', 'deploy/cloud/Caddyfile.cloud.template',
    'deploy/cloud/clucktalk-pilot.service', 'deploy/cloud/clucktalk-backup.service', 'deploy/cloud/clucktalk-backup.timer',
    'deploy/cloud/show-link.sh', 'deploy/cloud/rotate-token.sh', 'deploy/cloud/restore.sh', 'deploy/cloud/status.sh'
)
$Folders = @('src/clucktalk', 'data/seed', 'data/reference')   # whole folders, minus caches (below)

$stage = Join-Path ([System.IO.Path]::GetTempPath()) ('clucktalk-bundle-' + [guid]::NewGuid().ToString('N'))
$root = Join-Path $stage 'tree'
New-Item -ItemType Directory -Path $root | Out-Null
try {
    function Add-ToBundle([string]$Relative) {
        $from = Join-Path $RepoRoot $Relative
        if (-not (Test-Path -LiteralPath $from -PathType Leaf)) { throw "Allow-listed file is missing: $Relative" }
        $to = Join-Path $root $Relative
        New-Item -ItemType Directory -Force -Path (Split-Path $to) | Out-Null
        if ($Relative -match '\.(sh|service|timer|template|py|json|txt|toml|html|js|css|md)$') {
            # Text goes as LF with no BOM, so the shell scripts and unit files work on Linux.
            $text = [System.IO.File]::ReadAllText($from, [System.Text.Encoding]::UTF8) -replace "`r`n", "`n"
            [System.IO.File]::WriteAllText($to, $text, (New-Object System.Text.UTF8Encoding($false)))
        } else {
            Copy-Item -LiteralPath $from -Destination $to
        }
    }
    foreach ($f in $Files) { Add-ToBundle $f }
    foreach ($d in $Folders) {
        $base = Join-Path $RepoRoot $d
        if (-not (Test-Path -LiteralPath $base -PathType Container)) { throw "Allow-listed folder is missing: $d" }
        Get-ChildItem -LiteralPath $base -Recurse -File | Where-Object {
            $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and $_.Extension -notin '.pyc', '.pyo'
        } | ForEach-Object {
            Add-ToBundle ($_.FullName.Substring($RepoRoot.Length + 1) -replace '\\', '/')
        }
    }

    # ---- safety checks on what is about to be shipped (a second line of defence behind the allow-list) ------------
    $bad = Get-ChildItem -LiteralPath $root -Recurse -Force | Where-Object {
        $_.FullName.Substring($root.Length + 1) -match '(^|[\\/])(\.git|\.venv|\.local|private|node_modules|__pycache__|\.aws)([\\/]|$)' -or
        $_.Name -match '^(\.env.*|CLAUDE\.local\.md|.*\.(pem|key|sqlite3|db|log|bak))$'
    }
    if ($bad) { throw ('Refusing to build: a private or runtime file is in the bundle: ' + (($bad | ForEach-Object Name) -join ', ')) }
    $leaks = Get-ChildItem -LiteralPath $root -Recurse -File | Select-String -CaseSensitive -Pattern 'AKIA[0-9A-Z]{16}', 'BEGIN [A-Z ]*PRIVATE KEY', '(?i)TOKEN[S]?=[A-Za-z0-9._~-]{24,}' -List
    if ($leaks) { throw ('Refusing to build: something that looks like a secret is in: ' + (($leaks | ForEach-Object { $_.Path.Substring($root.Length + 1) }) -join ', ')) }

    $bundle = Join-Path $stage 'bundle.tar.gz'
    if (Get-Command $Tar -ErrorAction SilentlyContinue) {
        & $Tar -czf $bundle -C $root .
        if ($LASTEXITCODE -ne 0) { throw 'tar.exe failed to build the bundle.' }
    } elseif ($DryRun) {
        Write-Host '(tar.exe not found: the dry run lists the files but did not compress them.)'
    } else { throw 'tar.exe was not found.' }

    if ($BundleOut -ne '') { Copy-Item -LiteralPath $bundle -Destination $BundleOut -Force }
    $names = Get-ChildItem -LiteralPath $root -Recurse -File | ForEach-Object { $_.FullName.Substring($root.Length + 1) -replace '\\', '/' } | Sort-Object
    Write-Host ("Bundle: {0} files." -f $names.Count)
    if ($DryRun) {
        $names | ForEach-Object { Write-Host "  $_" }
        Write-Host ''
        Write-Host "DRY RUN: no connection was made. Hostname that would be used: https://$HostName"
        if ($FarmFile -ne '') { Write-Host 'The farm file would be uploaded separately (not part of the bundle).' }
        return
    }

    # ---- upload and run -------------------------------------------------------------------------------------------
    # accept-new: the server's host key is trusted the first time and checked on every later connection.
    $sshOpts = @('-i', $KeyPath, '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=accept-new', '-o', 'BatchMode=yes')
    $target = "$User@$ServerIp"
    $remoteStage = '/tmp/clucktalk-stage'

    & ssh.exe @sshOpts $target "rm -rf $remoteStage && umask 077 && mkdir $remoteStage"
    if ($LASTEXITCODE -ne 0) { throw 'Could not connect with ssh (check the IP, the key file and that port 22 is open in the Lightsail firewall).' }
    & scp.exe @sshOpts -q $bundle "${target}:$remoteStage/bundle.tar.gz"
    if ($LASTEXITCODE -ne 0) { throw 'scp of the bundle failed.' }
    $farmArg = ''
    if ($FarmFile -ne '') {
        & scp.exe @sshOpts -q $FarmFile "${target}:$remoteStage/farm.json"
        if ($LASTEXITCODE -ne 0) { throw 'scp of the farm file failed.' }
        $farmArg = " --farm-file $remoteStage/farm.json"
    }
    $remote = "cd $remoteStage && tar -xzf bundle.tar.gz ./deploy/cloud/bootstrap.sh && sudo bash ./deploy/cloud/bootstrap.sh --bundle $remoteStage/bundle.tar.gz --host $HostName$farmArg"
    & ssh.exe @sshOpts $target $remote
    if ($LASTEXITCODE -ne 0) { throw 'bootstrap.sh failed on the server (its last message is above). Fix it and run this script again: it is safe to repeat.' }

    Write-Host ''
    Write-Host "Done. HTTPS address: https://$HostName"
    Write-Host 'The farmer token was made on the server and is NOT shown here. To see the farmer link on the server screen, run:'
    Write-Host "  ssh -t -i `"$KeyPath`" $target sudo clucktalk-show-link"
    Write-Host 'Then check everything with:  .\deploy\cloud\verify.ps1 (see deploy\cloud\RUNBOOK.md).'
}
finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
