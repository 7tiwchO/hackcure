# HackCure n8n Workflow — Setup Guide

## Overview

HackCure uses two n8n workflows:

1. **Document Extraction Workflow** (`hackcure-document-extraction-workflow.json`):  
   Upload a doctor's report and/or prescription → Claude LLM extracts structured data → Saves as DRAFT in HackCure → Returns results with confidence scores and low-confidence highlights.

2. **Apply Confirmed Draft Workflow** (within the same file):  
   After the patient or doctor reviews and approves the draft, call the Apply webhook to activate the new care plan.

---

## Prerequisites

- **n8n** installed locally or on a server (v1.40+)
- **Anthropic API key** for Claude
- **HackCure backend** running (default: `http://localhost:8000`)

---

## Step 1: Install n8n

```bash
# Option A: npm (global install)
npm install -g n8n
n8n start

# Option B: Docker
docker run -it --rm --name n8n -p 5678:5678 \
  -v n8n_data:/home/node/.n8n \
  docker.n8n.io/n8nio/n8n
```

n8n will be accessible at: **http://localhost:5678**

---

## Step 2: Configure Credentials

### Anthropic API Key
1. Go to n8n Settings → Credentials → Add Credential
2. Type: **Header Auth**
3. Name: `Anthropic API Key`
4. Header Name: `x-api-key`
5. Header Value: Your Anthropic API key (from https://console.anthropic.com/)

---

## Step 3: Set Environment Variables

In n8n, go to Settings → Variables (or set as env vars):

| Variable | Description | Default |
|---|---|---|
| `HACKCURE_API_URL` | Backend API base URL | `http://localhost:8000` |
| `HACKCURE_AUTOMATION_KEY` | API key for automation endpoints | `hackcure-automation-dev-key-2026` |

---

## Step 4: Import Workflows

1. In n8n, go to **Workflows** → **Import from File**
2. Import `hackcure-document-extraction-workflow.json`
3. Activate the workflow

---

## Step 5: Test the Upload Flow

### Upload Documents (Doctor Report + Prescription)

```bash
# POST to the webhook with two documents as text
curl -X POST http://localhost:5678/webhook/hackcure-upload \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "YOUR_PATIENT_UUID",
    "rapport_base64": "Texte du rapport du médecin ici...",
    "ordonnance_base64": "Texte de l ordonnance ici..."
  }'
```

**Response** (Draft with confidence scores):
```json
{
  "drafts": [
    {
      "document_source_id": "uuid-1",
      "document_type": "DOCTOR_REPORT",
      "status": "DRAFT",
      "version": 1
    },
    {
      "document_source_id": "uuid-2",
      "document_type": "PRESCRIPTION",
      "status": "DRAFT",
      "version": 1
    }
  ],
  "low_confidence_fields": ["medicaments[0].Amoxicilline"],
  "requires_review": true,
  "avertissement": "Ces données extraites sont un BROUILLON..."
}
```

### Apply Confirmed Draft

```bash
curl -X POST http://localhost:5678/webhook/hackcure-apply \
  -H "Content-Type: application/json" \
  -d '{
    "document_source_ids": ["uuid-1", "uuid-2"],
    "confirmed_by": "patient"
  }'
```

**Response**:
```json
{
  "success": true,
  "prescription_id": "new-prescription-uuid",
  "treatment_summary_id": "new-summary-uuid",
  "doses_generated": 270,
  "sport_plans_created": 1,
  "nutrition_plans_created": 1,
  "old_reminders_cancelled": 42,
  "avertissement": "Traitement mis à jour avec succès..."
}
```

---

## Webhook URLs

| Webhook | URL | Method |
|---|---|---|
| Upload & Extract | `http://localhost:5678/webhook/hackcure-upload` | POST |
| Apply Draft | `http://localhost:5678/webhook/hackcure-apply` | POST |

---

## Security Notes

- The automation API key is transmitted via `X-Automation-Key` header
- Anthropic API key is stored in n8n credentials, NOT in the workflow JSON
- Medical data is sent to Anthropic Claude for extraction — this is the only external data transfer
- For privacy, consider self-hosting an open-source LLM (Mixtral, Llama) as an alternative

---

## Privacy-Friendly Alternative (No External API)

Replace the Claude HTTP nodes with a local LLM:
1. Install **Ollama** with `mistral` or `llama3` model
2. Change the Claude HTTP Request nodes to point to `http://localhost:11434/api/generate`
3. Use the same system prompt — local models support structured JSON output

This ensures zero medical data leaves your infrastructure.

---

## Patient Wellbeing Companion Workflows

The companion adds a chat workflow and three separate asynchronous workflows; import each JSON file individually:

- `chatbot-psychologique.workflow.json` receives authenticated backend requests, applies another safety/scope triage, fetches minimized patient context through the signed backend service endpoint, optionally searches vetted health sources, and returns the companion response. See the detailed [Chatbot n8n setup guide](../docs/CHATBOT_N8N_SETUP.md).

- `hackcure-companion-escalation-workflow.json` receives safety alerts and forwards a minimal event to the configured care contact endpoint.
- `hackcure-companion-daily-checkin-workflow.json` runs once a day and asks the backend to create an in-app wellbeing check-in for patients with chat consent.
- `hackcure-companion-weekly-summary-workflow.json` runs weekly and forwards aggregate mood data only for patients who separately enabled doctor sharing.

Set these n8n environment variables in the n8n host before activating schedules:

| Variable | Purpose |
|---|---|
| `HACKCURE_API_URL` | Reachable backend base URL, for example `http://host.docker.internal:8000` from Docker |
| `HACKCURE_CHAT_SHARED_SECRET` | Must match backend `CHAT_N8N_SHARED_SECRET` |
| `HACKCURE_ESCALATION_URL` | Configured doctor/caregiver alert receiver URL |
| `HACKCURE_ESCALATION_SECRET` | Secret expected by that alert receiver |
| `HACKCURE_CARE_TEAM_SUMMARY_URL` | Configured care-team weekly-summary receiver URL |
| `HACKCURE_CARE_TEAM_SECRET` | Secret expected by that summary receiver |

Set backend `CHAT_N8N_WEBHOOK_BASE_URL` to the n8n base URL and set the same `CHAT_N8N_SHARED_SECRET`. Use high-entropy secrets and TLS for traffic that leaves the local machine. The backend rejects internal workflow requests if the shared secret is unset or invalid.

The escalation payload omits message text and direct patient identifiers; it contains an internal patient reference and safety category. Weekly summaries include a patient reference, check-in count, and average mood. The endpoint filters to explicit doctor-sharing consent. n8n workflow settings disable success, failure, manual, and progress execution payload storage; also verify global n8n retention and execution-pruning settings.

The destination URLs are intentionally deployment-configured and are not populated in exported workflow JSON. Configure and test them with synthetic data before activation. The daily workflow writes in-app notifications; it does not send an external reminder.
