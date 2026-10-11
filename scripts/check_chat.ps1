param(
    [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"
$diagnosticToken = $env:CHAT_DIAGNOSTIC_TOKEN
$patientToken = $env:CHAT_TEST_ACCESS_TOKEN
$conversationId = $env:CHAT_TEST_CONVERSATION_ID

if (-not $diagnosticToken) {
    throw "Set CHAT_DIAGNOSTIC_TOKEN to the protected service token configured in backend/.env."
}
if (-not $patientToken -or -not $conversationId) {
    throw "Set CHAT_TEST_ACCESS_TOKEN and CHAT_TEST_CONVERSATION_ID for a synthetic, consented test patient. Do not use real patient data."
}

$headers = @{ "X-Chat-Diagnostics-Token" = $diagnosticToken }
$health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/chat/health" -Headers $headers -TimeoutSec 10
$health | ConvertTo-Json -Depth 5

$failed = $false
if (-not $health.backend.reachable) { Write-Host "FAIL backend" -ForegroundColor Red; $failed = $true } else { Write-Host "PASS backend" -ForegroundColor Green }
foreach ($name in @("reachable", "workflow_active", "secret_accepted")) {
    if ($health.n8n.$name) { Write-Host "PASS n8n.$name" -ForegroundColor Green }
    else { Write-Host "FAIL n8n.$name" -ForegroundColor Red; $failed = $true }
}
if ($health.anthropic.reachable) { Write-Host "PASS anthropic.reachable" -ForegroundColor Green }
else { Write-Host "FAIL anthropic.reachable" -ForegroundColor Red; $failed = $true }

$body = @{
    conversation_id = $conversationId
    client_message_id = [guid]::NewGuid().ToString()
    content = "Bonjour, peux-tu me dire comment tu peux m'accompagner ?"
} | ConvertTo-Json
$chatHeaders = @{ Authorization = "Bearer $patientToken"; "Content-Type" = "application/json" }
$reply = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/chat/messages" -Headers $chatHeaders -Body $body -TimeoutSec 45
if ($reply.fallback) {
    Write-Host "FAIL chat reply: $($reply.error_code); fallback returned (no AI response)." -ForegroundColor Red
    $failed = $true
} else {
    Write-Host "PASS chat reply: triage=$($reply.triage_label), language=$($reply.language)" -ForegroundColor Green
}

if ($failed) { exit 1 }
