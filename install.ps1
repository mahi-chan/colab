# gpu-bridge installer for Windows (PowerShell).
#
#   irm https://raw.githubusercontent.com/mahi-chan/gpu-bridge/main/install.ps1 | iex
#
# It downloads gpu-bridge to %USERPROFILE%\.gpu-bridge\app, sets up its Python environment,
# registers it with every AI client found on this computer, and adds a `gpu-bridge` command.
# Run the same line again to update. To pass options, set them first:
#
#   $env:GPU_BRIDGE_ARGS = "--client cursor"; irm <same address> | iex
#
# Inside a checkout of the repository, `.\install.ps1` installs from that checkout instead.

function Install-GpuBridge {
    $ErrorActionPreference = "Stop"
    $ProgressPreference = "SilentlyContinue"   # downloads are far faster without the progress bar

    $Repo   = if ($env:GPU_BRIDGE_REPO_SLUG) { $env:GPU_BRIDGE_REPO_SLUG } else { "mahi-chan/gpu-bridge" }
    $Branch = if ($env:GPU_BRIDGE_BRANCH) { $env:GPU_BRIDGE_BRANCH } else { "main" }
    $AppDir = if ($env:GPU_BRIDGE_DIR) { $env:GPU_BRIDGE_DIR } else { Join-Path $env:USERPROFILE ".gpu-bridge\app" }
    $BinDir = if ($env:GPU_BRIDGE_BIN) { $env:GPU_BRIDGE_BIN } else { Join-Path $env:USERPROFILE ".local\bin" }
    $InstallArgs = @($args)
    if ($env:GPU_BRIDGE_ARGS) { $InstallArgs += $env:GPU_BRIDGE_ARGS.Split(" ", [StringSplitOptions]::RemoveEmptyEntries) }
    $StartDir = (Get-Location).Path

    try {
        # 1. Find the code: this checkout if we are in one, otherwise download it.
        $Project = Join-Path $StartDir "pyproject.toml"
        if ((Test-Path $Project) -and (Select-String -Path $Project -Pattern '^name = "gpu-bridge"' -Quiet)) {
            $AppDir = $StartDir
            Write-Host "Using the checkout at $AppDir"
        } else {
            Write-Host "Downloading gpu-bridge to $AppDir"
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

        # 4. Add a `gpu-bridge` command.
        $Exe = Join-Path $AppDir ".venv\Scripts\gpu-bridge.exe"
        New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
        Set-Content -Path (Join-Path $BinDir "gpu-bridge.cmd") -Value "@`"$Exe`" %*" -Encoding ASCII
        $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
        if (-not (($UserPath -split ";") -contains $BinDir)) {
            [Environment]::SetEnvironmentVariable("Path", "$BinDir;$UserPath", "User")
        }

        # 5. Register with AI clients.
        Write-Host ""
        & $Exe install @InstallArgs
        if ($LASTEXITCODE -ne 0) { throw "Registering with AI clients failed." }

        Write-Host ""
        Write-Host "The 'gpu-bridge' command is available in new terminals."
    } finally {
        Set-Location $StartDir
    }
}

Install-GpuBridge @args
