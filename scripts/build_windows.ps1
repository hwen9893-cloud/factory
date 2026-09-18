param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildVenv = Join-Path $ProjectRoot ".build-venv-windows"
$WorkDir = Join-Path $ProjectRoot "build\windows"
$PortableDir = Join-Path $ProjectRoot "release\windows\portable"
$InstallerDir = Join-Path $ProjectRoot "release\windows\installer"
$ExePath = Join-Path $PortableDir "StoryFactory\StoryFactory.exe"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "Windows package must be built on Windows 10/11; PyInstaller is not a cross-compiler."
}
if (-not [Environment]::Is64BitOperatingSystem) {
    throw "Story Factory supports Windows 10/11 64-bit only."
}

$Python = Get-Command py -ErrorAction SilentlyContinue
if ($null -eq $Python) {
    throw "Python launcher (py.exe) was not found. Install 64-bit Python 3.11 or 3.12 for the build machine."
}

Push-Location $ProjectRoot
try {
    if (-not (Test-Path $BuildVenv)) {
        & py -3.12 -m venv $BuildVenv
        if ($LASTEXITCODE -ne 0) {
            & py -3.11 -m venv $BuildVenv
        }
    }
    $BuildPython = Join-Path $BuildVenv "Scripts\python.exe"
    if (-not (Test-Path $BuildPython)) {
        throw "Unable to create the isolated build environment."
    }

    & $BuildPython -m pip install --upgrade pip
    & $BuildPython -m pip install -e ".[desktop,models,test]"
    & $BuildPython scripts\generate_icons.py
    & $BuildPython -m pytest -q

    foreach ($Target in @($WorkDir, $PortableDir)) {
        if (Test-Path $Target) {
            Remove-Item -Recurse -Force $Target
        }
    }
    New-Item -ItemType Directory -Force $PortableDir | Out-Null
    New-Item -ItemType Directory -Force $InstallerDir | Out-Null

    & $BuildPython -m PyInstaller --noconfirm --clean `
        --distpath $PortableDir `
        --workpath $WorkDir `
        StoryFactory.spec
    if (-not (Test-Path $ExePath)) {
        throw "Portable build did not produce $ExePath"
    }

    $Version = & $BuildPython -c "from factory.version import __version__; print(__version__)"
    if (-not $SkipInstaller) {
        $CompilerCandidates = @()
        if (${env:ProgramFiles(x86)}) {
            $CompilerCandidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
        }
        if ($env:ProgramFiles) {
            $CompilerCandidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
        }
        $CompilerCandidates = @($CompilerCandidates | Where-Object { Test-Path $_ })
        if ($CompilerCandidates.Count -eq 0) {
            Write-Warning "Inno Setup 6 was not found; portable build is complete, installer was skipped."
        } else {
            & $CompilerCandidates[0] "/DMyAppVersion=$Version" "installer\storyfactory.iss"
        }
    }

    Write-Host "Portable build: $PortableDir\StoryFactory"
    if (Test-Path $InstallerDir) {
        Write-Host "Installer output: $InstallerDir"
    }
} finally {
    Pop-Location
    if (Test-Path $BuildVenv) {
        Write-Host "Build environment retained at $BuildVenv for reproducible incremental builds."
    }
}
