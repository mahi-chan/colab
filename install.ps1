# thesis-mcp installer for Windows (PowerShell).
#
#   .\install.ps1                      install into every AI client found on this computer
#   .\install.ps1 --client cursor      install into one client (repeatable)
#   .\install.ps1 --print              only print the config entry, change nothing
#
# Run it from a checkout of the repository, or on its own (it then downloads the
# repository to %USERPROFILE%\.thesis-mcp\app). Safe to run again.
$ErrorActionPreference = "Stop"

$RepoUrl = if ($env:THESIS_MCP_REPO) { $env:THESIS_MCP_REPO } else { "https://github.com/mahi-chan/colab.git" }
$Branch  = if ($env:THESIS_MCP_BRANCH) { $env:THESIS_MCP_BRANCH } else { "claude/mcp-colab-kaggle-3nheg4" }
$AppDir  = if ($env:THESIS_MCP_DIR) { $env:THESIS_MCP_DIR } else { Join-Path $env:USERPROFILE ".thesis-mcp\app" }

function Test-Command($Name) { return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

# 1. Find the code: this checkout if we are in one, otherwise download it.
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$Project = Join-Path $ScriptDir "pyproject.toml"
if ((Test-Path $Project) -and (Select-String -Path $Project -Pattern '^name = "thesis-mcp"' -Quiet)) {
    $AppDir = $ScriptDir
    Write-Host "Using the checkout at $AppDir"
} else {
    if (-not (Test-Command git)) { throw "git is required. Install it from https://git-scm.com, then run this again." }
    if (Test-Path (Join-Path $AppDir ".git")) {
        Write-Host "Updating $AppDir"
        git -C $AppDir pull --ff-only --quiet
    } else {
        Write-Host "Downloading thesis-mcp to $AppDir"
        New-Item -ItemType Directory -Force -Path (Split-Path $AppDir) | Out-Null
        git clone --quiet --branch $Branch $RepoUrl $AppDir
    }
    if ($LASTEXITCODE -ne 0) { throw "git failed." }
}

# 2. Make sure uv (the Python package manager this project uses) is available.
$env:Path = (Join-Path $env:USERPROFILE ".local\bin") + ";" + $env:Path
if (-not (Test-Command uv)) {
    Write-Host "Installing uv (https://docs.astral.sh/uv/)"
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    if (-not (Test-Command uv)) { throw "uv was installed but is not on PATH. Open a new terminal and run this again." }
}

# 3. Create the environment with the exact pinned versions.
Write-Host "Installing dependencies"
Set-Location $AppDir
uv sync --locked --no-dev --inexact --quiet
if ($LASTEXITCODE -ne 0) { throw "Installing dependencies failed." }

# 4. Register with AI clients.
Write-Host ""
uv run --no-sync thesis-mcp install @args
exit $LASTEXITCODE
