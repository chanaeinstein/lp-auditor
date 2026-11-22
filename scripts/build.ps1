# PyInstaller one-file console build -> dist/agent.exe
# Usage (from anywhere): powershell -ExecutionPolicy Bypass -File scripts\build.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        throw "No .venv found - create it and run: pip install -r requirements.txt"
    }

    & $python -m PyInstaller `
        --noconfirm --clean --onefile --console `
        --name agent `
        --paths $root `
        --add-data "agent/knowledge/rules.md;agent/knowledge" `
        --add-data "agent/models.yaml;agent" `
        --collect-submodules langgraph `
        --collect-submodules langchain_openai `
        --copy-metadata langgraph `
        --copy-metadata langsmith `
        --copy-metadata langchain-core `
        --copy-metadata langchain-openai `
        --exclude-module pytest `
        --exclude-module tkinter `
        agent/cli.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

    $exe = Join-Path $root "dist\agent.exe"
    $sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "[INFO] Built $exe ($sizeMb MB)"
}
finally {
    Pop-Location
}
