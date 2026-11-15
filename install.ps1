# thesis-mcp installer for Windows (PowerShell).
#
#   irm https://raw.githubusercontent.com/mahi-chan/colab/claude/mcp-colab-kaggle-3nheg4/install.ps1 | iex
#
# It downloads thesis-mcp to %USERPROFILE%\.thesis-mcp\app, sets up its Python environment,
# registers it with every AI client found on this computer, and adds a `thesis-mcp` command.
# Run the same line again to update. To pass options, set them first:
#
#   $env:THESIS_MCP_ARGS = "--client cursor"; irm <same address> | iex
#
# Inside a checkout of the repository, `.\install.ps1` installs from that checkout instead.

function Install-ThesisMcp {
    $ErrorActionPreference = "Stop"
    $ProgressPreference = "SilentlyContinue"   # downloads are far faster without the progress bar

    $Repo   = if ($env:THESIS_MCP_REPO_SLUG) { $env:THESIS_MCP_REPO_SLUG } else { "mahi-chan/colab" }
    $Branch = if ($env:THESIS_MCP_BRANCH) { $env:THESIS_MCP_BRANCH } else { "claude/mcp-colab-kaggle-3nheg4" }
    $AppDir = if ($env:THESIS_MCP_DIR) { $env:THESIS_MCP_DIR } else { Join-Path $env:USERPROFILE ".thesis-mcp\app" }
    $BinDir = if ($env:THESIS_MCP_BIN) { $env:THESIS_MCP_BIN } else { Join-Path $env:USERPROFILE ".local\bin" }
    $InstallArgs = @($args)
    if ($env:THESIS_MCP_ARGS) { $InstallArgs += $env:THESIS_MCP_ARGS.Split(" ", [StringSplitOptions]::RemoveEmptyEntries) }
    $StartDir = (Get-Location).Path

    try {
        # 1. Find the code: this checkout if we are in one, otherwise download it.
        $Project = Join-Path $StartDir "pyproject.toml"
        if ((Test-Path $Project) -and (Select-String -Path $Project -Pattern '^name = "thesis-mcp"' -Quiet)) {
            $AppDir = $StartDir
            Write-Host "Using the checkout at $AppDir"
        } else {
            Write-Host "Downloading thesis-mcp to $AppDir"
            $New = "$AppDir.new"
            $Zip = "$AppDir.zip"
            if (Test-Path $New) { Remove-Item -Recurse -Force $New }
            New-Item -ItemType Directory -Force -Path $New | Out-Null
            Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/$Repo/archive/refs/heads/$Branch.zip" -OutFile $Zip
            Expand-Archive -Path $Zip -DestinationPath $New -Force
            Remove-Item -Force $Zip
            $Inner = Get-ChildItem -Path $New -Directory | Select-Object -First 1
            if (-not $Inner) { throw "The download did not contain the project." }
            # keep the existing environment so an update is quick
            $OldEnv = Join-Path $AppDir ".venv"
            if (Test-Path $OldEnv) { Move-Item -Path $OldEnv -Destination (Join-Path $Inner.FullName ".venv") }
            if (Test-Path $AppDir) { Remove-Item -Recurse -Force $AppDir }
            Move-Item -Path $Inner.FullName -Destination $AppDir
            Remove-Item -Recurse -Force $New
        }

        # 2. Make sure uv (the Python package manager this project uses) is available.
        $env:Path = (Join-Path $env:USERPROFILE ".local\bin") + ";" + $env:Path
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            Write-Host "Installing uv (https://docs.astral.sh/uv/)"
            Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
            if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
                throw "uv was installed but is not on PATH. Open a new terminal and run this again."
            }
        }

        # 3. Create the environment with the exact pinned versions.
        Write-Host "Installing dependencies"
        Set-Location $AppDir
        uv sync --locked --no-dev --inexact --quiet
        if ($LASTEXITCODE -ne 0) { throw "Installing dependencies failed." }

        # 4. Add a `thesis-mcp` command.
        $Exe = Join-Path $AppDir ".venv\Scripts\thesis-mcp.exe"
        New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
        Set-Content -Path (Join-Path $BinDir "thesis-mcp.cmd") -Value "@`"$Exe`" %*" -Encoding ASCII
        $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
        if (-not (($UserPath -split ";") -contains $BinDir)) {
            [Environment]::SetEnvironmentVariable("Path", "$BinDir;$UserPath", "User")
        }

        # 5. Register with AI clients.
        Write-Host ""
        & $Exe install @InstallArgs
        if ($LASTEXITCODE -ne 0) { throw "Registering with AI clients failed." }

        Write-Host ""
        Write-Host "The 'thesis-mcp' command is available in new terminals."
    } finally {
        Set-Location $StartDir
    }
}

Install-ThesisMcp @args
