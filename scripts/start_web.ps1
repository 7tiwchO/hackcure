# Start the backend and Expo Web locally without editing mobile/.env.
$ErrorActionPreference = 'Stop'
$rootDir = (Get-Item $PSScriptRoot).Parent.FullName
$backendDir = Join-Path $rootDir 'backend'
$mobileDir = Join-Path $rootDir 'mobile'
$backendPython = Join-Path $backendDir '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $backendPython)) {
    throw "Backend virtual environment is missing. From '$backendDir', run: python -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.txt"
}

$backendCommand = "Set-Location '$backendDir'; & '$backendPython' -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
$mobileCommand = "Set-Location '$mobileDir'; `$env:EXPO_PUBLIC_API_URL='http://localhost:8000'; npx expo start --web"

Write-Host 'Opening backend and Expo Web in separate PowerShell windows.' -ForegroundColor Cyan
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $backendCommand)
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $mobileCommand)
Write-Host 'Web app: http://localhost:8081' -ForegroundColor Green
