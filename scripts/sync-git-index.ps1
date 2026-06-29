# Refresh .git/index from the writable index so Cursor/VS Code source control matches reality.
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "git-env.ps1")
git read-tree HEAD | Out-Null
Sync-GitIndexToRepo
Write-Host "Synced .git/index with HEAD."
