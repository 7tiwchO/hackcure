# Demarre le backend de l'application patient sur le port 8100, relie a Hospital Copilot (suppose deja lance sur 8000).
#   .\scripts\start_with_hospital.ps1                 # backend seul (http://localhost:8100)
#   .\scripts\start_with_hospital.ps1 -Web            # + Expo web dans une seconde fenetre
#   .\scripts\start_with_hospital.ps1 -HospitalUrl http://localhost:8010 -Port 8100
# Le jeton de service est lu dans ..\Hospital_copilot\.env (PLATFORM_SERVICE_TOKEN) s'il n'est pas deja dans l'environnement.
# Sans credit d'API : l'agent et le chatbot passent seuls en mode de secours (regles et reponses preparees).
param(
    [int]$Port = 8100,
    [string]$HospitalUrl = "http://localhost:8000",
    [string]$HospitalEnv = "",
    [switch]$Web,
    [switch]$NoSeed,
    [switch]$Validation   # sans ce commutateur le programme est applique automatiquement (mode demonstration)
)
$ErrorActionPreference = 'Stop'
$rootDir = (Get-Item $PSScriptRoot).Parent.FullName
$backendDir = Join-Path $rootDir 'backend'
$mobileDir = Join-Path $rootDir 'mobile'
$backendPython = Join-Path $backendDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $backendPython)) {
    throw "Environnement Python absent. Depuis '$backendDir' : python -m venv .venv ; .venv\Scripts\python.exe -m pip install -r requirements.txt (voir RAPPORT_APP.md si l'installation echoue avec Python 3.13)"
}

if (-not $env:HOSPITAL_COPILOT_SERVICE_TOKEN) {
    if (-not $HospitalEnv) { $HospitalEnv = Join-Path (Split-Path -Parent $rootDir) 'Hospital_copilot\.env' }
    if (Test-Path -LiteralPath $HospitalEnv) {
        $line = Get-Content -LiteralPath $HospitalEnv | Where-Object { $_ -match '^\s*PLATFORM_SERVICE_TOKEN\s*=' } | Select-Object -First 1
        if ($line) { $env:HOSPITAL_COPILOT_SERVICE_TOKEN = ($line -split '=', 2)[1].Trim().Trim('"') }
    }
}
if (-not $env:HOSPITAL_COPILOT_SERVICE_TOKEN) {
    Write-Host "ATTENTION : HOSPITAL_COPILOT_SERVICE_TOKEN introuvable (ni dans l'environnement ni dans $HospitalEnv). La liaison echouera." -ForegroundColor Yellow
}
$env:HOSPITAL_COPILOT_URL = $HospitalUrl
if (-not $Validation) { $env:DEMO_AUTO_APPLY = "true" }

try {
    $health = Invoke-RestMethod -Uri "$HospitalUrl/health" -TimeoutSec 4
    Write-Host "Hospital Copilot repond sur $HospitalUrl (version $($health.version))." -ForegroundColor Green
} catch {
    Write-Host "Hospital Copilot ne repond pas sur $HospitalUrl : l'application demarre quand meme (derniere synchronisation conservee)." -ForegroundColor Yellow
}

Set-Location $backendDir
if (-not $NoSeed) {
    & $backendPython -m app.seeds.seed_data
    & $backendPython -m app.seeds.seed_hospital_demo --sync
}
if ($Web) {
    $mobileCommand = "Set-Location '$mobileDir'; `$env:EXPO_PUBLIC_API_URL='http://localhost:$Port'; npx expo start --web --host localhost"
    Start-Process powershell -ArgumentList @('-NoExit', '-Command', $mobileCommand)
}
Write-Host "Application patient : http://localhost:$Port/docs   (zohra@example.com / Test123!@#, liee a PAT-0004)" -ForegroundColor Green
& $backendPython -m uvicorn app.main:app --host 0.0.0.0 --port $Port
