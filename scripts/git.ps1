# Git wrapper that uses a writable index path on Windows/Cursor sandboxes.
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$GitArgs
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "git-env.ps1")

if ($GitArgs.Count -eq 0) {
    git
    exit $LASTEXITCODE
}

& git @GitArgs
$exitCode = $LASTEXITCODE
Sync-GitIndexToRepo
exit $exitCode
