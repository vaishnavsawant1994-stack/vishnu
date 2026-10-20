param(
    [string]$DataDirectory = (Join-Path $env:TEMP 'vishnu-pixel-preview'),
    [int]$Port = 8770
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
$env:CONTROL_SERVER_PORT = [string]$Port
$env:PERSONAL_AI_IPHONE_ALLOW_INSECURE = '1'
# This launcher is intentionally a fresh, loopback-only development runtime;
# ignore any owner bootstrap secret inherited from the shell or a .env file.
$env:PERSONAL_AI_BOOTSTRAP_SECRET = ''
Remove-Item Env:PERSONAL_AI_IPHONE_ENROLLMENT_CODE -ErrorAction SilentlyContinue

Write-Host "Starting the Vishnu web app with isolated local development data: $dataRoot"
Write-Host "Web app: http://127.0.0.1:$Port/web/"
Write-Host "Screens 11-15 sample preview: http://127.0.0.1:$Port/web/campaign-demo"
Push-Location $repoRoot
try {
    & $python -m scripts.run_local_web
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
