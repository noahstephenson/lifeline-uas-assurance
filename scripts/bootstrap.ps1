$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    if (-not (Test-Path -LiteralPath ".venv")) { py -3.11 -m venv .venv }
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
    Push-Location openmct
    try { npm install } finally { Pop-Location }
    .\.venv\Scripts\lifeline.exe --json doctor
    .\.venv\Scripts\lifeline.exe validate
} finally {
    Pop-Location
}

