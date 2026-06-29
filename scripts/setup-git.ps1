# One-time local Git setup for this repo (hooks, index path, VS Code terminal env).
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$vscodeDir = Join-Path $repoRoot ".vscode"
$settingsPath = Join-Path $vscodeDir "settings.json"

. (Join-Path $PSScriptRoot "git-env.ps1")
$localIndex = ($env:GIT_INDEX_FILE -replace "\\", "/")

Write-Host "Setting up Git tooling for $repoRoot"
Write-Host "Git index path: $localIndex"

& (Join-Path $PSScriptRoot "repair-git.ps1")

New-Item -ItemType Directory -Force -Path $vscodeDir | Out-Null

$envBlock = @"
  "terminal.integrated.env.windows": {
    "GIT_INDEX_FILE": "$localIndex"
  }
"@

if (Test-Path -LiteralPath $settingsPath) {
    $raw = Get-Content -Raw -LiteralPath $settingsPath
    if ($raw -match '"terminal\.integrated\.env\.windows"') {
        Write-Host "Updated existing VS Code settings at $settingsPath"
        $raw = $raw -replace '"GIT_INDEX_FILE"\s*:\s*"[^"]*"', "`"GIT_INDEX_FILE`": `"$localIndex`""
        Set-Content -LiteralPath $settingsPath -Value $raw -Encoding utf8
    }
    else {
        $trimmed = $raw.TrimEnd()
        if ($trimmed.EndsWith("}")) {
            $insert = "," + [Environment]::NewLine + $envBlock + [Environment]::NewLine + "}"
            $raw = $trimmed.Substring(0, $trimmed.Length - 1) + $insert
            Set-Content -LiteralPath $settingsPath -Value $raw -Encoding utf8
        }
        else {
            throw "Could not merge VS Code settings; edit $settingsPath manually."
        }
    }
}
else {
    @"
{
$envBlock
}
"@ | Set-Content -LiteralPath $settingsPath -Encoding utf8
    Write-Host "Created $settingsPath"
}

Write-Host "Setup complete. Open a new terminal or run: . scripts/git-env.ps1"
