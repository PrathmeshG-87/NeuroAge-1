param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$virtualEnvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $backendRoot -PathType Container)) {
    throw "Backend folder not found: $backendRoot"
}

if (Test-Path $virtualEnvPython -PathType Leaf) {
    $python = $virtualEnvPython
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw 'Python was not found. Create the project virtual environment or install Python.'
    }
    $python = $pythonCommand.Source
}

Push-Location $backendRoot
try {
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload
    if ($LASTEXITCODE -ne 0) {
        throw "Backend exited with code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}
