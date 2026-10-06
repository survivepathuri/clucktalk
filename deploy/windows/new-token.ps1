<#
.SYNOPSIS
  Makes the pilot's two random tokens and puts them into pilot.env (outside the repository).
.DESCRIPTION
  Uses the operating system's cryptographic random generator (32 bytes per token). A token is written only where the
  file still has a placeholder or nothing, so existing tokens are never overwritten. The file is then restricted to the
  current user. The farmer link is printed on the screen ONLY when a farmer token was just made (or with -ShowLink);
  it is never written to a file or a log. Nothing else is printed about a token.
#>
param(
    [string]$PilotRoot = 'C:\clucktalk-pilot',
    [switch]$ShowLink
)
. (Join-Path $PSScriptRoot 'common.ps1')

$paths = Get-PilotPaths $PilotRoot
New-Item -ItemType Directory -Force -Path (Split-Path $paths.EnvFile) | Out-Null
if (-not (Test-Path -LiteralPath $paths.EnvFile)) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'env.windows.example') -Destination $paths.EnvFile
    Write-Host "Created $($paths.EnvFile) from the example. Edit the public address and the paths in it."
}

function New-RandomToken {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    # URL-safe base64 without padding: 43 characters from A-Z a-z 0-9 - _ (accepted by the server's token rule).
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$lines = [System.Collections.Generic.List[string]](Get-Content -LiteralPath $paths.EnvFile)
$made = @{}
foreach ($name in 'CLUCKTALK_SIMULATOR_TOKENS', 'CLUCKTALK_AUTH_TOKEN') {
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^$name=(.*)$") {
            if (Test-Placeholder $Matches[1].Trim()) {
                $lines[$i] = "$name=$(New-RandomToken)"
                $made[$name] = $true
            }
            break
        }
    }
}
$text = ($lines -join "`n") + "`n"
[System.IO.File]::WriteAllText($paths.EnvFile, $text, (New-Object System.Text.UTF8Encoding($false)))
Restrict-ToCurrentUser $paths.EnvFile

if ($made.Count -eq 0) { Write-Host 'Both tokens already exist; nothing was changed.' }
else { Write-Host ("Made {0} new token(s) in {1}." -f $made.Count, $paths.EnvFile) }

if ($made.ContainsKey('CLUCKTALK_SIMULATOR_TOKENS') -or $ShowLink) {
    $values = Read-PilotEnv $paths.EnvFile
    $origin = $values['CLUCKTALK_PUBLIC_ORIGIN']
    if (Test-Placeholder $origin) {
        Write-Host 'CLUCKTALK_PUBLIC_ORIGIN in pilot.env is still a placeholder: set it, then run  new-token.ps1 -ShowLink  to see the link.'
        exit 0
    }
    $first = ($values['CLUCKTALK_SIMULATOR_TOKENS'] -split ',')[0].Trim()
    Write-Host ''
    Write-Host 'Farmer link (shown on this screen only; it is not saved anywhere else; do not paste it into a chat or a log):'
    Write-Host "$origin/#t=$first"
}
else {
    Write-Host 'The farmer link is not shown again by default. Use  new-token.ps1 -ShowLink  to display it on this screen.'
}
