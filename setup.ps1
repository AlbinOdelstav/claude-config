# setup.ps1 — Install Claude Code configuration to ~/.claude
# Run from the repo root: .\setup.ps1
# Optional: .\setup.ps1 -GitBashPath "D:/Git/bin/bash.exe"
param(
    [string]$ClaudeDir    = "$env:USERPROFILE\.claude",
    [string]$GitBashPath  = "C:/Program Files/Git/bin/bash.exe"
)

$ErrorActionPreference = 'Stop'
$RepoDir = $PSScriptRoot

# Forward-slash version of ClaudeDir for JSON paths (bash/Claude expect forward slashes)
$ClaudeDirFwd = $ClaudeDir.Replace('\', '/')

Write-Host "Installing Claude Code config to: $ClaudeDir"

# Ensure target directories exist
foreach ($sub in @('', 'agents', 'skills', 'skills\implement')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $ClaudeDir $sub) | Out-Null
}

# Copy scripts and config files
$filesToCopy = @(
    'CLAUDE.md',
    'notify.ps1',
    'focus-terminal.ps1',
    'statusline-command.sh'
)
foreach ($f in $filesToCopy) {
    Copy-Item (Join-Path $RepoDir $f) (Join-Path $ClaudeDir $f) -Force
    Write-Host "  Copied $f"
}

# Copy agents
Get-ChildItem (Join-Path $RepoDir 'agents') -Filter '*.md' | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $ClaudeDir "agents\$($_.Name)") -Force
    Write-Host "  Copied agents/$($_.Name)"
}

# Copy skills
Copy-Item (Join-Path $RepoDir 'skills\implement\SKILL.md') `
          (Join-Path $ClaudeDir 'skills\implement\SKILL.md') -Force
Write-Host "  Copied skills/implement/SKILL.md"

# Generate settings.json from template, substituting paths
$template = Get-Content (Join-Path $RepoDir 'settings-template.json') -Raw
$settings = $template `
    -replace '\{\{CLAUDE_DIR\}\}', $ClaudeDirFwd `
    -replace '\{\{GIT_BASH\}\}',   $GitBashPath

$settingsPath = Join-Path $ClaudeDir 'settings.json'
if (Test-Path $settingsPath) {
    $backup = "$settingsPath.bak"
    Copy-Item $settingsPath $backup -Force
    Write-Host "  Backed up existing settings.json -> settings.json.bak"
}
$settings | Set-Content $settingsPath -Encoding UTF8 -NoNewline
Write-Host "  Generated settings.json"

Write-Host ""
Write-Host "Done. Restart Claude Code for changes to take effect."
Write-Host "If Git Bash is not at '$GitBashPath', re-run with: .\setup.ps1 -GitBashPath 'your\path\bash.exe'"
