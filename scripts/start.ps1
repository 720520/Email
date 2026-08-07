[CmdletBinding()]
param(
    [string]$AdminUsername = "admin",
    [switch]$NoBrowser,
    [switch]$SetupOnly
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$utf8Encoding = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8Encoding
[Console]::OutputEncoding = $utf8Encoding
$OutputEncoding = $utf8Encoding
$env:PYTHONIOENCODING = "utf-8"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Resolve-Path (Join-Path $scriptDirectory "..")).Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$frontendDirectory = Join-Path $projectRoot "frontend"
$codexDependencies = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$FailureMessage
    )
    & $FilePath @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code: $LASTEXITCODE)"
    }
}

function Get-Executable {
    param([string[]]$Names)
    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            return $command.Source
        }
    }
    return $null
}

function Test-NativeCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments = @()
    )
    # Windows PowerShell 5.1 在全局 Stop 模式下会把原生命令的 stderr
    # 转成异常；探测命令失败本来是正常分支，因此这里只依据退出码判断。
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & $FilePath @Arguments *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Get-Winget {
    $winget = Get-Executable -Names @("winget.exe", "winget")
    if (-not $winget) {
        $windowsAppsWinget = Join-Path $env:LocalAppData "Microsoft\WindowsApps\winget.exe"
        if (Test-Path -LiteralPath $windowsAppsWinget) {
            $winget = $windowsAppsWinget
        }
    }
    if (-not $winget) {
        throw "winget is unavailable. Install Python 3.11/3.12 and Node.js 22/24, then run again."
    }
    return $winget
}

function Test-PythonVersion {
    param(
        [string]$Executable,
        [string[]]$PrefixArguments = @()
    )
    return Test-NativeCommand -FilePath $Executable -Arguments @(
        $PrefixArguments + @("-c", "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)")
    )
}

function Try-CreateVenv {
    $launcher = Get-Executable -Names @("py.exe", "py")
    if ($launcher) {
        foreach ($version in @("-3.12", "-3.11")) {
            if (Test-PythonVersion -Executable $launcher -PrefixArguments @($version)) {
                Invoke-Checked -FilePath $launcher -Arguments @($version, "-m", "venv", ".venv") -FailureMessage "Failed to create Python virtual environment"
                return $true
            }
        }
    }

    $python = Get-Executable -Names @("python.exe", "python")
    if ($python -and (Test-PythonVersion -Executable $python)) {
        Invoke-Checked -FilePath $python -Arguments @("-m", "venv", ".venv") -FailureMessage "Failed to create Python virtual environment"
        return $true
    }

    $knownPython = Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"
    if ((Test-Path -LiteralPath $knownPython) -and (Test-PythonVersion -Executable $knownPython)) {
        Invoke-Checked -FilePath $knownPython -Arguments @("-m", "venv", ".venv") -FailureMessage "Failed to create Python virtual environment"
        return $true
    }
    $codexPython = Join-Path $codexDependencies "python\python.exe"
    if ((Test-Path -LiteralPath $codexPython) -and (Test-PythonVersion -Executable $codexPython)) {
        Invoke-Checked -FilePath $codexPython -Arguments @("-m", "venv", ".venv") -FailureMessage "Failed to create Python virtual environment"
        return $true
    }
    return $false
}

function Ensure-PythonEnvironment {
    if (Test-Path -LiteralPath $venvPython) {
        return
    }

    Write-Step "Creating Python virtual environment"
    if (Try-CreateVenv) {
        return
    }

    Write-Host "Supported Python not found. Installing Python 3.12 with winget..." -ForegroundColor Yellow
    $winget = Get-Winget
    Invoke-Checked -FilePath $winget -Arguments @(
        "install", "--id", "Python.Python.3.12", "--exact", "--silent",
        "--accept-package-agreements", "--accept-source-agreements"
    ) -FailureMessage "Python 3.12 installation failed"
    Refresh-ProcessPath
    if (-not (Try-CreateVenv)) {
        throw "Python was installed but could not be located. Reopen Windows and run this launcher again."
    }
}

function Ensure-BackendDependencies {
    $projectFile = Join-Path $projectRoot "backend\pyproject.toml"
    $markerFile = Join-Path $projectRoot ".venv\.fund-nav-pyproject.sha256"
    $expectedHash = (Get-FileHash -LiteralPath $projectFile -Algorithm SHA256).Hash
    $installedHash = if (Test-Path -LiteralPath $markerFile) {
        (Get-Content -LiteralPath $markerFile -Raw).Trim()
    } else {
        ""
    }

    $importsReady = Test-NativeCommand -FilePath $venvPython -Arguments @(
        "-c", "import alembic, cryptography, fastapi, imapclient, openpyxl, pandas, sqlalchemy, uvicorn, xlrd"
    )
    if ($importsReady -and $installedHash -eq $expectedHash) {
        return
    }

    Write-Step "Installing backend dependencies"
    Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip") -FailureMessage "pip upgrade failed"
    Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pip", "install", "-e", ".\backend") -FailureMessage "Backend dependency installation failed"
    Set-Content -LiteralPath $markerFile -Value $expectedHash -Encoding ASCII
}

function Ensure-Node {
    $node = Get-Executable -Names @("node.exe", "node")
    if (-not $node) {
        $knownNode = "C:\Program Files\nodejs\node.exe"
        if (Test-Path -LiteralPath $knownNode) {
            $node = $knownNode
        }
    }
    if (-not $node) {
        $codexNode = Join-Path $codexDependencies "node\bin\node.exe"
        if (Test-Path -LiteralPath $codexNode) {
            $node = $codexNode
            $env:Path = "$(Split-Path -Parent $codexNode);$env:Path"
        }
    }
    if (-not $node) {
        Write-Step "Installing Node.js LTS with winget"
        $winget = Get-Winget
        Invoke-Checked -FilePath $winget -Arguments @(
            "install", "--id", "OpenJS.NodeJS.LTS", "--exact", "--silent",
            "--accept-package-agreements", "--accept-source-agreements"
        ) -FailureMessage "Node.js installation failed"
        Refresh-ProcessPath
        $node = Get-Executable -Names @("node.exe", "node")
        if (-not $node -and (Test-Path -LiteralPath "C:\Program Files\nodejs\node.exe")) {
            $node = "C:\Program Files\nodejs\node.exe"
            $env:Path = "C:\Program Files\nodejs;$env:Path"
        }
    }
    if (-not $node) {
        throw "Node.js was installed but could not be located. Reopen Windows and run again."
    }

    $version = (& $node --version).Trim().TrimStart("v")
    $major = [int]($version.Split(".")[0])
    if ($major -lt 22) {
        throw "Node.js $version is too old. Version 22 or 24 is required."
    }
    if ($major -notin @(22, 24)) {
        Write-Host "Warning: Node.js $version is not the validated 22/24 LTS version." -ForegroundColor Yellow
    }
}

function Ensure-Pnpm {
    $pnpm = Get-Executable -Names @("pnpm.cmd", "pnpm")
    if (-not $pnpm) {
        $codexPnpm = Join-Path $codexDependencies "bin\fallback\pnpm.cmd"
        if (Test-Path -LiteralPath $codexPnpm) {
            $pnpm = $codexPnpm
        }
    }
    if ($pnpm) {
        $version = (& $pnpm --version).Trim()
        if ($LASTEXITCODE -eq 0 -and [int]($version.Split(".")[0]) -eq 11) {
            return $pnpm
        }
    }

    Write-Step "Installing pnpm 11"
    $npm = Get-Executable -Names @("npm.cmd", "npm")
    if (-not $npm -and (Test-Path -LiteralPath "C:\Program Files\nodejs\npm.cmd")) {
        $npm = "C:\Program Files\nodejs\npm.cmd"
    }
    if (-not $npm) {
        throw "npm was not found after Node.js installation."
    }
    Invoke-Checked -FilePath $npm -Arguments @("install", "--global", "pnpm@11.9.0") -FailureMessage "pnpm installation failed"
    Refresh-ProcessPath
    $pnpm = Get-Executable -Names @("pnpm.cmd", "pnpm")
    if (-not $pnpm) {
        $appDataPnpm = Join-Path $env:AppData "npm\pnpm.cmd"
        if (Test-Path -LiteralPath $appDataPnpm) {
            $pnpm = $appDataPnpm
        }
    }
    if (-not $pnpm) {
        $codexPnpm = Join-Path $codexDependencies "bin\fallback\pnpm.cmd"
        if (Test-Path -LiteralPath $codexPnpm) {
            $pnpm = $codexPnpm
        }
    }
    if (-not $pnpm) {
        throw "pnpm was installed but could not be located. Reopen Windows and run again."
    }
    return $pnpm
}

function Ensure-FrontendDependencies {
    param([string]$PnpmPath)
    $packageFile = Join-Path $frontendDirectory "package.json"
    $lockFile = Join-Path $frontendDirectory "pnpm-lock.yaml"
    $nodeModules = Join-Path $frontendDirectory "node_modules"
    $markerFile = Join-Path $nodeModules ".fund-nav-lock.sha256"
    $hashInput = (Get-FileHash -LiteralPath $packageFile -Algorithm SHA256).Hash + (Get-FileHash -LiteralPath $lockFile -Algorithm SHA256).Hash
    $expectedHashBytes = [Text.Encoding]::UTF8.GetBytes($hashInput)
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $expectedHash = -join ($sha256.ComputeHash($expectedHashBytes) | ForEach-Object { $_.ToString("x2") })
    } finally {
        $sha256.Dispose()
    }
    $installedHash = if (Test-Path -LiteralPath $markerFile) {
        (Get-Content -LiteralPath $markerFile -Raw).Trim()
    } else {
        ""
    }
    if ((Test-Path -LiteralPath $nodeModules) -and $installedHash -eq $expectedHash) {
        return
    }

    Write-Step "Installing frontend dependencies"
    Push-Location $frontendDirectory
    try {
        Invoke-Checked -FilePath $PnpmPath -Arguments @("install", "--frozen-lockfile") -FailureMessage "Frontend dependency installation failed"
        Set-Content -LiteralPath $markerFile -Value $expectedHash -Encoding ASCII
    } finally {
        Pop-Location
    }
}

function Test-LocalPort {
    param([int]$Port)
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        return $task.Wait(500) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Test-HttpEndpoint {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

try {
    Set-Location $projectRoot
    Write-Host "Fund Operations Console - one-click launcher" -ForegroundColor Green
    Write-Host "Project: $projectRoot"

    Ensure-PythonEnvironment
    Ensure-BackendDependencies
    Ensure-Node
    $pnpmPath = Ensure-Pnpm
    Ensure-FrontendDependencies -PnpmPath $pnpmPath

    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot ".env"))) {
        Write-Step "Creating local .env"
        Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination (Join-Path $projectRoot ".env")
    }

    Write-Step "Initializing security keys"
    Invoke-Checked -FilePath $venvPython -Arguments @("-m", "app.cli.init_security_keys") -FailureMessage "Security key initialization failed"

    Write-Step "Applying database migrations"
    Invoke-Checked -FilePath $venvPython -Arguments @("-m", "alembic", "-c", "backend\alembic.ini", "upgrade", "head") -FailureMessage "Database migration failed"

    if ($SetupOnly) {
        Write-Host "Environment preparation completed successfully." -ForegroundColor Green
        exit 0
    }

    $adminCount = (& $venvPython -c "from sqlalchemy import func, select; from app.db.models import AppUser; from app.db.session import get_database_manager; s=get_database_manager().session_factory(); print(s.scalar(select(func.count(AppUser.id)).where(AppUser.is_active.is_(True), AppUser.is_platform_admin.is_(True))) or 0); s.close()").Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect the administrator account."
    }
    if ([int]$adminCount -eq 0) {
        Write-Step "Creating the first administrator"
        Write-Host "Enter a password of at least 10 characters. Input is hidden." -ForegroundColor Yellow
        Invoke-Checked -FilePath $venvPython -Arguments @("-m", "app.cli.create_admin", "--username", $AdminUsername) -FailureMessage "Administrator creation failed"
    }

    $escapedRoot = $projectRoot.Replace("'", "''")
    $escapedPython = $venvPython.Replace("'", "''")
    $escapedFrontend = $frontendDirectory.Replace("'", "''")
    $escapedPnpm = $pnpmPath.Replace("'", "''")
    $shell = Get-Executable -Names @("powershell.exe", "pwsh.exe")
    if (-not $shell) {
        throw "PowerShell executable was not found."
    }

    if (-not (Test-HttpEndpoint -Url "http://127.0.0.1:8000/api/v1/health/live")) {
        if (Test-LocalPort -Port 8000) {
            throw "Port 8000 is occupied by another program. Close it and run again."
        }
        Write-Step "Starting backend on http://127.0.0.1:8000"
        $backendCommand = "`$Host.UI.RawUI.WindowTitle='Fund NAV Backend'; Set-Location -LiteralPath '$escapedRoot'; & '$escapedPython' -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000"
        Start-Process -FilePath $shell -ArgumentList @("-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand)
    } else {
        Write-Host "Backend is already running." -ForegroundColor Yellow
    }

    if (-not (Test-HttpEndpoint -Url "http://127.0.0.1:5173")) {
        if (Test-LocalPort -Port 5173) {
            throw "Port 5173 is occupied by another program. Close it and run again."
        }
        Write-Step "Starting frontend on http://127.0.0.1:5173"
        $frontendCommand = "`$Host.UI.RawUI.WindowTitle='Fund NAV Frontend'; Set-Location -LiteralPath '$escapedFrontend'; & '$escapedPnpm' dev --host 127.0.0.1 --port 5173"
        Start-Process -FilePath $shell -ArgumentList @("-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand)
    } else {
        Write-Host "Frontend is already running." -ForegroundColor Yellow
    }

    Write-Step "Waiting for the web console"
    $ready = $false
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ((Test-HttpEndpoint -Url "http://127.0.0.1:8000/api/v1/health/live") -and (Test-HttpEndpoint -Url "http://127.0.0.1:5173")) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }

    if ($ready) {
        Write-Host "System started successfully: http://127.0.0.1:5173" -ForegroundColor Green
        if (-not $NoBrowser) {
            Start-Process "http://127.0.0.1:5173"
        }
    } else {
        Write-Host "Processes were started but readiness timed out. Check the two service windows." -ForegroundColor Yellow
    }
    Write-Host "Close the service windows or press Ctrl+C in them to stop the system."
    exit 0
} catch {
    Write-Host ""
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Fix the issue shown above, then run the launcher again."
    exit 1
}
