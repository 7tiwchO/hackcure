# Chatbot psychologique: n8n setup

## What this workflow does

`n8n/chatbot-psychologique.workflow.json` is an inactive, importable n8n workflow. The authenticated mobile client calls FastAPI. The persistent `/api/v1/chat/messages` route checks consent and stores conversation history in the backend; the Sakina screen's `/api/chat` route keeps history in mobile memory and does not store its transcript. When both `CHAT_N8N_CHAT_WEBHOOK_URL` and `CHAT_N8N_SHARED_SECRET` are configured, FastAPI sends the complete bounded transcript (up to 40 messages) through this n8n webhook. The workflow validates the secret and request limits, fetches patient/session-scoped minimized context from the backend, performs safety/scope triage, returns a safety or off-topic response when needed, and otherwise generates the reply. The LLM receives no patient name, address, phone, or context token.

For general current health/wellbeing questions, triage may create a search query. The query is scrubbed of email, phone, and UUID patterns and sent to Tavily with source domains restricted to WHO, NHS, Mayo Clinic, and Tunisia's health ministry. Search results are untrusted input; the system prompt directs the model to cite used source links and ignore instructions found in pages. Leave `TAVILY_API_KEY` unset to disable search.

## Required configuration

1. Start n8n (the repository has no n8n service/version pinned in `docker-compose.yml` or a root package manifest). Import `n8n/chatbot-psychologique.workflow.json` through **Workflows → Import from File**.
2. In the n8n process environment, set:

   | Variable | Value |
   |---|---|
   | `HACKCURE_CHAT_SHARED_SECRET` | The same high-entropy secret as backend `CHAT_N8N_SHARED_SECRET` |
   | `HACKCURE_API_URL` | Backend base URL reachable *from n8n*; in a Docker container on Windows use `http://host.docker.internal:8000` |
   | `HACKCURE_ANTHROPIC_API_KEY` | Anthropic API key, stored only in n8n environment/secret manager |
   | `CHAT_MODEL` | `claude-sonnet-5-5` by default |
   | `TRIAGE_MODEL` | `claude-haiku-5-5` by default |
   | `TAVILY_API_KEY` | Optional Tavily key; omit to disable web search |

3. The workflow reads environment variables in n8n expressions. On self-hosted n8n versions that block expression access to environment variables, enable `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`, protect the n8n host and workflow editors, and keep workflow execution data retention disabled. If your n8n version disallows this setting, replace environment expressions with n8n credentials/variables before activating.
4. In `backend/.env`, set `CHAT_N8N_CHAT_WEBHOOK_URL=http://localhost:5678/webhook/hackcure-companion-chat`, `CHAT_N8N_SHARED_SECRET` to the same secret, and `CHAT_N8N_WEBHOOK_BASE_URL=http://localhost:5678` for the health/escalation/daily/weekly webhooks. Restart FastAPI after changing environment values. If n8n is intentionally not used, set `ANTHROPIC_API_KEY` in `backend/.env` for direct backend replies.
5. Set a separate random `CHAT_DIAGNOSTIC_TOKEN` in `backend/.env` to protect `GET /api/v1/chat/health`. The endpoint calls `/webhook/hackcure-companion-health` with the shared-secret header and probes the backend's Anthropic model-list endpoint without sending patient text. This does not prove that the separate chat workflow is active or that the Anthropic key stored in n8n is valid; confirm those with a synthetic live chat request.
6. Verify the workflow's `Save successful executions`, `Save failed executions`, and progress/execution data retention are disabled globally as well as in the workflow. Do not use manual test executions with real patient content.
7. Import the escalation, daily check-in, and weekly-summary workflows separately. Configure their existing destination variables as described in `n8n/SETUP_GUIDE.md`. Keep those schedules inactive until a clinician/care-team destination has been reviewed and consent behavior tested.

The backend's internal context endpoint requires both the shared secret and an HMAC token bound to the authorized patient ID and conversation/session ID. It returns only minimized prescription/report facts. Do not expose this endpoint outside the trusted backend/n8n connection.

## Testing the flow

1. Use a synthetic patient, grant chat consent, and confirm backend `GET /health` works.
2. Test with a normal wellbeing message, own-prescription question, unrelated request, medication-change request, emergency, and self-harm statement. Confirm the response JSON contains `reply`, `triage_label`, `language`, and `safety_flag`.
3. Use an unrelated message (for example a car-price or coding request) and confirm the workflow does not answer it.
4. Use an in-scope general health question and verify cited links come only from the allowed search domains. Without a Tavily key, confirm the companion still replies without citations.
5. Use two synthetic patient accounts: replay another session's context token and confirm the backend rejects it. Confirm a patient cannot fetch another patient's conversation through the public API.
6. Check n8n executions and host logs contain no stored message bodies. Never test crisis escalation against a real caregiver until consent and destination behavior are approved.

## Current verification limit

This checkout has no n8n version in its compose/package manifests, no Docker executable, and no running n8n instance available to import into. The local backend also currently has no Anthropic API key or chat webhook/shared-secret configured. The workflow can be statically parsed here, but live import, credential resolution, and the 30-message provider-backed run require a configured n8n instance, an Anthropic key in n8n (or in backend for direct mode), and optionally a Tavily key. The included `backend/tests/evals/companion_triage.json` is a review/eval set, not evidence of a live model run or clinical certification.
