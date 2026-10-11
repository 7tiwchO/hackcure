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

if ($health.backend.reachable) { Write-Host "PASS A app-to-backend" -ForegroundColor Green }
else { Write-Host "FAIL A app-to-backend" -ForegroundColor Red; $failed = $true }

if ($health.sakina_route -eq "n8n") {
    if ($health.n8n.reachable) { Write-Host "PASS B backend-to-n8n" -ForegroundColor Green }
    else { Write-Host "FAIL B backend-to-n8n: $($health.n8n.reason)" -ForegroundColor Red; $failed = $true }
    if ($health.n8n.secret_accepted) { Write-Host "PASS C webhook shared-secret" -ForegroundColor Green }
    else { Write-Host "FAIL C webhook shared-secret" -ForegroundColor Red; $failed = $true }
    if ($health.n8n.chat_workflow_active) { Write-Host "PASS D n8n chat workflow active" -ForegroundColor Green }
    else { Write-Host "FAIL D n8n chat workflow inactive" -ForegroundColor Red; $failed = $true }
    Write-Host "INFO n8n owns the Anthropic credential; health checks its validity with the synthetic chat request below." -ForegroundColor Cyan
} else {
    Write-Host "PASS B direct Anthropic route selected; n8n is not used by Sakina." -ForegroundColor Cyan
    Write-Host "PASS C n8n shared-secret not applicable to direct route." -ForegroundColor Cyan
    Write-Host "PASS D n8n activation not applicable to direct route." -ForegroundColor Cyan
    if ($health.anthropic.reachable) { Write-Host "PASS Anthropic API key/reachability" -ForegroundColor Green }
    else { Write-Host "FAIL Anthropic API key/reachability: $($health.anthropic.reason)" -ForegroundColor Red; $failed = $true }
}

if ($health.timeouts.backend_chat_seconds -ge 30 -and $health.timeouts.sakina_mobile_seconds -gt $health.timeouts.backend_chat_seconds) {
    Write-Host "PASS G timeouts: backend=$($health.timeouts.backend_chat_seconds)s mobile=$($health.timeouts.sakina_mobile_seconds)s" -ForegroundColor Green
} else {
    Write-Host "FAIL G timeout budget is invalid or too short" -ForegroundColor Red
    $failed = $true
}

$chatHeaders = @{ Authorization = "Bearer $patientToken"; "Content-Type" = "application/json" }
$persistentBody = @{
    conversation_id = $conversationId
    client_message_id = [guid]::NewGuid().ToString()
    content = "Bonjour, peux-tu me dire comment tu peux m'accompagner ?"
} | ConvertTo-Json
$persistentReply = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/chat/messages" -Headers $chatHeaders -Body $persistentBody -TimeoutSec 75
if ($persistentReply.fallback) {
    Write-Host "FAIL E persistent chat: $($persistentReply.error_code); fallback returned." -ForegroundColor Red
    $failed = $true
} elseif ($persistentReply.reply -and $persistentReply.triage_label -and $persistentReply.language -and $null -ne $persistentReply.fallback) {
    Write-Host "PASS E persistent backend chat and F response contract: triage=$($persistentReply.triage_label), language=$($persistentReply.language)" -ForegroundColor Green
} else {
    Write-Host "FAIL F persistent chat response contract" -ForegroundColor Red
    $failed = $true
}

$sakinaBody = @{ history = @(@{ role = "user"; content = "Je me sens anxieux" }) } | ConvertTo-Json -Depth 5
$sakinaReply = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/chat" -Headers $chatHeaders -Body $sakinaBody -TimeoutSec 75
if ($sakinaReply.fallback) {
    Write-Host "FAIL Sakina screen endpoint: $($sakinaReply.error_code); fallback returned." -ForegroundColor Red
    $failed = $true
} else {
    Write-Host "PASS E Sakina screen endpoint returned a live reply." -ForegroundColor Green
    if ($sakinaReply.reply -and $null -ne $sakinaReply.triage_label -and $null -ne $sakinaReply.fallback) {
        Write-Host "PASS F Sakina response contract: triage=$($sakinaReply.triage_label)" -ForegroundColor Green
    } else {
        Write-Host "FAIL F Sakina response contract" -ForegroundColor Red
        $failed = $true
    }
    if ($sakinaReply.triage_label -eq "distress") { Write-Host "PASS H distress routes to ordinary support" -ForegroundColor Green }
    else { Write-Host "FAIL H expected distress triage, received $($sakinaReply.triage_label)" -ForegroundColor Red; $failed = $true }
    $sakinaReply | ConvertTo-Json -Depth 5
}

$crisisBody = @{ history = @(@{ role = "user"; content = "Je veux me faire du mal" }) } | ConvertTo-Json -Depth 5
$crisisReply = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/chat" -Headers $chatHeaders -Body $crisisBody -TimeoutSec 10
if ($crisisReply.crisis -and -not $crisisReply.fallback -and $crisisReply.emergency_numbers.Count -gt 0) {
    Write-Host "PASS H crisis route returned configured emergency resources." -ForegroundColor Green
} else {
    Write-Host "FAIL H crisis route or emergency resources." -ForegroundColor Red
    $failed = $true
}

if ($failed) { exit 1 }
