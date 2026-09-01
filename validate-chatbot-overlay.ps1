[CmdletBinding()]
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$overlayRoot = Join-Path $packageRoot "chatbot-overlay"

Push-Location $overlayRoot
try {
    & $Python -m compileall -q src
    if ($LASTEXITCODE -ne 0) { throw "Python compilation failed." }

    & $Python -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw "Python tests failed." }

    & $Python -m ruff check src tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff failed." }

    & $Python -m ruff format --check src tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff formatting check failed." }

    & $Python -m mypy --strict src tests
    if ($LASTEXITCODE -ne 0) { throw "Strict mypy failed." }

    & $Python -m bandit -r src -q
    if ($LASTEXITCODE -ne 0) { throw "Bandit failed." }

    node --check ..\frontend-reference\script.js
    if ($LASTEXITCODE -ne 0) { throw "Frontend reference syntax check failed." }

    node --test ..\frontend-reference\tests\stt-frontend.test.mjs
    if ($LASTEXITCODE -ne 0) { throw "Frontend reference tests failed." }

    Write-Host "Azure STT chatbot overlay validation passed." -ForegroundColor Green
    Write-Host "No live Azure call, secret access or deployment was performed."
}
finally {
    Pop-Location
}
