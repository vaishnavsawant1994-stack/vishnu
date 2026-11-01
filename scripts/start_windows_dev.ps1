param(
    [string]$DataDirectory = (Join-Path $env:TEMP 'vishnu-owner-fresh-20261023'),
    [int]$WebPort = 8771
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Vishnu virtual environment not found at $python"
}
$dataRoot = [System.IO.Path]::GetFullPath($DataDirectory)
$null = New-Item -ItemType Directory -Force -Path $dataRoot

$env:PERSONAL_AI_DATA_DIR = $dataRoot
$env:CONTROL_SERVER_HOST = '127.0.0.1'
$env:CONTROL_SERVER_PORT = [string]$WebPort
$env:PERSONAL_AI_IPHONE_ALLOW_INSECURE = '1'
$env:PERSONAL_AI_BOOTSTRAP_SECRET = ''
$env:CONTROL_SERVER_ENABLED = 'true'
$env:VISHNU_WEB_APP_URL = "http://127.0.0.1:$WebPort/web/"
Remove-Item Env:PERSONAL_AI_IPHONE_ENROLLMENT_CODE -ErrorAction SilentlyContinue

Write-Host "Starting Vishnu Windows desktop with shared local dev data: $dataRoot"
Write-Host "Web app: http://127.0.0.1:$WebPort/web/"
Write-Host "Screens 11-15 preview: http://127.0.0.1:$WebPort/web/campaign-demo"
Write-Host 'The desktop window displays Vishnu Web directly, so both surfaces use the same UI and runtime.'
Push-Location $repoRoot
try {
    & $python -m app.main
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
