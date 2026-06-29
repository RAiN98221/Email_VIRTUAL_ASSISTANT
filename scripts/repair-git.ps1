# Repair common Git issues on Windows (stale index, sandbox ACL blocks, stale locks).
param(
    [switch]$SkipAcl
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    $root = git rev-parse --show-toplevel 2>$null
    if (-not $root) {
        throw "Run this script from inside the repository."
    }
    return (Resolve-Path $root).Path
}

function Remove-DenyRules {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return 0
    }

    try {
        $acl = Get-Acl -LiteralPath $Path
        $removed = 0
        foreach ($rule in @($acl.Access | Where-Object { $_.AccessControlType -eq "Deny" })) {
            if ($acl.RemoveAccessRule($rule)) {
                $removed++
            }
        }
        if ($removed -gt 0) {
            Set-Acl -LiteralPath $Path -AclObject $acl
        }
        return $removed
    }
    catch {
        Write-Host "Could not remove deny ACL on ${Path}: $($_.Exception.Message)"
        return 0
    }
}

function Reset-Acl {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    try {
        icacls $Path /inheritance:r /grant:r "${env:USERNAME}:(F)" "SYSTEM:(F)" "Administrators:(F)" | Out-Null
    }
    catch {
        Write-Host "Could not reset ACL on ${Path}: $($_.Exception.Message)"
    }
}

function Reset-TreeAcl {
    param([string]$Path)

    try {
        icacls $Path /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" | Out-Null
    }
    catch {
        Write-Host "Could not reset tree ACL on ${Path}: $($_.Exception.Message)"
    }
}

function Get-LocalIndexPath {
    param([string]$RepoRoot)

    . (Join-Path $PSScriptRoot "git-env.ps1")
    return $env:GIT_INDEX_FILE
}

function Ensure-HooksPath {
    param([string]$RepoRoot)

    Push-Location $RepoRoot
    try {
        $current = git config --get core.hooksPath 2>$null
        if ($current -ne ".githooks") {
            git config core.hooksPath .githooks
            Write-Host "Configured core.hooksPath=.githooks"
        }
        if ((git config --get core.autocrlf 2>$null) -ne "false") {
            git config core.autocrlf false
            Write-Host "Configured core.autocrlf=false"
        }
    }
    finally {
        Pop-Location
    }
}

function Remove-StaleLocks {
    param([string]$RepoRoot)

    Get-ChildItem -LiteralPath (Join-Path $RepoRoot ".git") -Filter "*.lock" -File -ErrorAction SilentlyContinue |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Force
            Write-Host "Removed stale lock: $($_.Name)"
        }
}

function Sync-IndexFromHead {
    param(
        [string]$RepoRoot,
        [string]$IndexPath
    )

    $localDir = Split-Path $IndexPath -Parent
    New-Item -ItemType Directory -Force -Path $localDir | Out-Null

    Push-Location $RepoRoot
    try {
        $previous = $env:GIT_INDEX_FILE
        $env:GIT_INDEX_FILE = $IndexPath
        git read-tree HEAD | Out-Null

        $gitIndex = Join-Path $RepoRoot ".git/index"
        try {
            Copy-Item -LiteralPath $IndexPath -Destination $gitIndex -Force
            Write-Host "Rebuilt index from HEAD at $IndexPath and synced .git/index"
        }
        catch {
            Write-Host "Rebuilt index from HEAD at $IndexPath (.git/index sync skipped: $($_.Exception.Message))"
        }
    }
    finally {
        if ($null -eq $previous) {
            Remove-Item Env:GIT_INDEX_FILE -ErrorAction SilentlyContinue
        }
        else {
            $env:GIT_INDEX_FILE = $previous
        }
        Pop-Location
    }
}

function Test-IndexWritable {
    param([string]$Path)

    $previous = $env:GIT_INDEX_FILE
    try {
        $env:GIT_INDEX_FILE = $Path
        git read-tree HEAD 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
    finally {
        if ($null -eq $previous) {
            Remove-Item Env:GIT_INDEX_FILE -ErrorAction SilentlyContinue
        }
        else {
            $env:GIT_INDEX_FILE = $previous
        }
    }
}

$repoRoot = Get-RepoRoot
$gitDir = Join-Path $repoRoot ".git"
$gitIndex = Join-Path $gitDir "index"
$localIndex = Get-LocalIndexPath -RepoRoot $repoRoot

Write-Host "Repairing Git state in $repoRoot"

Ensure-HooksPath -RepoRoot $repoRoot
Remove-StaleLocks -RepoRoot $repoRoot

if (-not $SkipAcl) {
    $denyIndex = Remove-DenyRules -Path $gitIndex
    $denyGit = Remove-DenyRules -Path $gitDir
    if ($denyIndex -gt 0 -or $denyGit -gt 0) {
        Write-Host "Removed deny ACL rules (index=$denyIndex, .git=$denyGit)"
    }

    Reset-Acl -Path $gitIndex
    Reset-TreeAcl -Path $gitDir
    Write-Host "Reset ACLs on .git/index and .git"
}

Sync-IndexFromHead -RepoRoot $repoRoot -IndexPath $localIndex

Push-Location $repoRoot
try {
    git status -sb
}
finally {
    Pop-Location
}

if (Test-IndexWritable -Path $localIndex) {
    Write-Host "Git index repair complete."
    Write-Host "Use scripts/git.ps1 for add/commit/push in Cursor, or run: . scripts/git-env.ps1"
}
else {
    Write-Host "Warning: index is still not writable. Use scripts/git.ps1 for Git commands." -ForegroundColor Yellow
}
