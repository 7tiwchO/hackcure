# HackCure full-system verification. Tests use disposable SQLite databases.
$ErrorActionPreference = 'Stop'
$rootDir = (Get-Item $PSScriptRoot).Parent.FullName
$backendDir = Join-Path $rootDir 'backend'
$mobileDir = Join-Path $rootDir 'mobile'
$backendPython = Join-Path $backendDir '.venv\Scripts\python.exe'
$oldDatabaseUrl = $env:DATABASE_URL
$testDb = Join-Path $env:TEMP "hackcure-check-$PID.db"
$migrationDb = Join-Path $env:TEMP "hackcure-migration-check-$PID.db"
$results = [ordered]@{}

if (-not (Test-Path -LiteralPath $backendPython)) {
    Write-Error "Backend virtual environment not found. Create it in '$backendDir' and install requirements.txt first."
}

function Invoke-Check([string]$Name, [scriptblock]$Command) {
    Write-Host "`n$Name" -ForegroundColor Yellow
    & $Command
    if ($LASTEXITCODE -eq 0) {
        $script:results[$Name] = 'PASS'
        Write-Host '  PASS' -ForegroundColor Green
    } else {
        $script:results[$Name] = 'FAIL'
        Write-Host '  FAIL' -ForegroundColor Red
    }
}

try {
    $sourceDb = Join-Path $backendDir 'hackcure.db'
    if (Test-Path -LiteralPath $sourceDb) {
        $sourceSqlite = $sourceDb.Replace('\', '/')
        $targetSqlite = $testDb.Replace('\', '/')
        & $backendPython -c "import sqlite3; s=sqlite3.connect(r'$sourceSqlite'); d=sqlite3.connect(r'$targetSqlite'); s.backup(d); d.close(); s.close()"
        if ($LASTEXITCODE -ne 0) { throw 'Could not make the disposable SQLite test copy.' }
    }

    $testSqliteUrl = 'sqlite+aiosqlite:///' + $testDb.Replace('\', '/')
    $env:DATABASE_URL = $testSqliteUrl
    Push-Location $backendDir
    try {
        Invoke-Check 'Prepare disposable test database' { & $backendPython -m app.seeds.seed_data }
        Invoke-Check 'Backend pytest suite (disposable database)' { & $backendPython -m pytest tests/ -q -W ignore }
        Invoke-Check 'Fresh Alembic migration' {
            $env:DATABASE_URL = 'sqlite+aiosqlite:///' + $migrationDb.Replace('\', '/')
            & $backendPython -m alembic upgrade head
            $env:DATABASE_URL = $testSqliteUrl
        }
        Invoke-Check 'FastAPI health endpoint' {
            $healthCheck = @'
import asyncio
import httpx
from app.main import app

async def main():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200 and response.json().get("status") == "ok"

asyncio.run(main())
'@
            & $backendPython -c $healthCheck
        }
    } finally {
        Pop-Location
    }

    Push-Location $mobileDir
    try {
        Invoke-Check 'Mobile TypeScript' { npx tsc --noEmit }
        Invoke-Check 'Mobile lint' { npm run lint }
        Invoke-Check 'Expo dependency compatibility' { npx expo install --check }
    } finally {
        Pop-Location
    }

    Push-Location $rootDir
    try {
        Invoke-Check 'n8n workflow JSON and connection references' {
            $workflowCheck = @'
import glob
import json
import sys

files = glob.glob("n8n/*.json")
for path in files:
    with open(path, encoding="utf-8") as handle:
        workflow = json.load(handle)
    nodes = {node["name"] for node in workflow.get("nodes", [])}
    for source, outputs in workflow.get("connections", {}).items():
        if source not in nodes:
            sys.exit(f"{path}: missing connection source {source}")
        for edges in outputs.values():
            for edge_group in edges:
                for edge in edge_group:
                    if edge.get("node") not in nodes:
                        sys.exit(f"{path}: missing connection target {edge.get('node')}")
print(f"Validated {len(files)} workflow files")
'@
            & $backendPython -c $workflowCheck
        }
    } finally {
        Pop-Location
    }
} finally {
    $env:DATABASE_URL = $oldDatabaseUrl
    foreach ($path in @($testDb, $migrationDb, "$testDb-wal", "$testDb-shm", "$migrationDb-wal", "$migrationDb-shm")) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }
}

Write-Host "`nVerification summary" -ForegroundColor Cyan
$results.GetEnumerator() | ForEach-Object {
    $color = if ($_.Value -eq 'PASS') { 'Green' } else { 'Red' }
    Write-Host ("  [{0}] {1}" -f $_.Value, $_.Key) -ForegroundColor $color
}
if ($results.Values -contains 'FAIL') { exit 1 }
