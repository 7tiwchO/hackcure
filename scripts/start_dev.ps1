# Start the backend and Expo for physical-device development without editing mobile/.env.
$ErrorActionPreference = 'Stop'
$rootDir = (Get-Item $PSScriptRoot).Parent.FullName
$backendDir = Join-Path $rootDir 'backend'
$mobileDir = Join-Path $rootDir 'mobile'
$backendPython = Join-Path $backendDir '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $backendPython)) {
    throw "Backend virtual environment is missing. From '$backendDir', run: python -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.txt"
}

$ipObj = Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi*', 'Ethernet*' -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '169.254*' -and $_.IPAddress -notlike '127.*' } |
    Select-Object -First 1
if (-not $ipObj) {
    throw 'Could not find a Wi-Fi/Ethernet IPv4 address. Connect the PC to the same Wi-Fi as the phone and check ipconfig.'
}

$localIP = $ipObj.IPAddress
$backendCommand = "Set-Location '$backendDir'; & '$backendPython' -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
$mobileCommand = "Set-Location '$mobileDir'; `$env:EXPO_PUBLIC_API_URL='http://${localIP}:8000'; npx expo start -c --lan"

Write-Host "Backend API: http://${localIP}:8000" -ForegroundColor Green
Write-Host 'Opening backend and Expo in separate PowerShell windows. Scan Expo Go QR on the same Wi-Fi.' -ForegroundColor Cyan
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $backendCommand)
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $mobileCommand)
