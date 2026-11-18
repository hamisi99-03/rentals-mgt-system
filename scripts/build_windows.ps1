param(
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Create the .venv first (see docs/RUNNING.md)."
}

Write-Host "Building Rentals Manager with PyInstaller..."
& ".venv\Scripts\python.exe" -m PyInstaller --noconfirm rentals.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Write-Host "Build complete: dist\RentalsManager\RentalsManager.exe"

if ($Installer) {
    $iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $candidates = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
        )
        foreach ($candidate in $candidates) {
            if (Test-Path $candidate) { $iscc = Get-Item $candidate; break }
        }
    }
    if (-not $iscc) {
        Write-Warning "Inno Setup (ISCC.exe) was not found. Install Inno Setup 6, then run: iscc installer.iss"
        exit 0
    }
    $isccPath = if ($iscc -is [System.Management.Automation.CommandInfo]) { $iscc.Source } else { $iscc.FullName }
    Write-Host "Building installer..."
    & $isccPath "installer.iss"
}
