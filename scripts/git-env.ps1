# Resolve a stable, writable Git index path for this repo (outside sandbox-locked .git/index).
function Get-GitIndexPath {
    param([string]$RepoRoot)

    $normalized = (Resolve-Path $RepoRoot).Path.ToLowerInvariant()
    $hash = [BitConverter]::ToString(
        [System.Security.Cryptography.SHA256]::Create().ComputeHash(
            [System.Text.Encoding]::UTF8.GetBytes($normalized)
        )
    ).Replace("-", "").Substring(0, 16).ToLowerInvariant()

    $dir = Join-Path $env:LOCALAPPDATA "email_virtual_assistant/git-indexes"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return Join-Path $dir "$hash.index"
}

# Dot-source this file to route Git's index outside sandbox-locked .git/index.
# Usage: . .\scripts\git-env.ps1

$repoRoot = git rev-parse --show-toplevel 2>$null
if (-not $repoRoot) {
    Write-Error "git-env.ps1 must be sourced from inside the repository."
    return
}

$indexPath = Get-GitIndexPath -RepoRoot $repoRoot
$env:GIT_INDEX_FILE = $indexPath

if (-not (Test-Path -LiteralPath $indexPath)) {
    git read-tree HEAD | Out-Null
}

function Sync-GitIndexToRepo {
    if (-not $env:GIT_INDEX_FILE) {
        return
    }
    $root = git rev-parse --show-toplevel 2>$null
    if (-not $root) {
        return
    }
    $target = Join-Path $root ".git/index"
    try {
        Copy-Item -LiteralPath $env:GIT_INDEX_FILE -Destination $target -Force
    }
    catch {
        Write-Warning "Could not sync .git/index for the IDE: $($_.Exception.Message)"
    }
}
