# Companion chat pipeline diagnosis

## Call path

1. `mobile/src/features/companion/CompanionScreen.tsx` selects the latest patient conversation (or creates one if none exists), then calls `companionApi.send`.
2. `mobile/src/services/api/companion.ts` sends `POST /api/v1/chat/messages` with the authenticated bearer token, conversation ID, a stable client message ID, and the text.
3. `backend/app/api/companion.py` enforces patient role, conversation ownership, consent, and rate limits, runs triage, handles crisis/medication-change paths locally, and loads recent history for ordinary replies.
4. `backend/app/services/companion.py` calls the active n8n chat webhook when URL and shared secret are configured; otherwise it calls Anthropic directly. The n8n path validates its secret and scoped context token, retrieves minimized context from FastAPI, triages scope/safety, optionally searches allowed health sources, calls Anthropic, normalizes the reply, and responds to the webhook.
5. The backend validates n8n response wrappers and returns `MessageResponse`; `fallback=true` indicates a service reply could not be generated. Fallback assistant text is returned to the current request but is not stored or added to memory. Retrying uses the same client message ID.

## Root cause observed in this workspace

The repeated English reply is emitted by the backend fallback. The configured `backend/.env` contains no `ANTHROPIC_API_KEY`, `CHAT_N8N_CHAT_WEBHOOK_URL`, or `CHAT_N8N_SHARED_SECRET` (values were checked only for presence, never printed). With no n8n URL, `ask_companion` attempts direct Anthropic; `_anthropic` raises `RuntimeError("chat provider is not configured")` when the key is empty, and the previous broad exception handler returned its fixed English response. It then stored that text as an ordinary assistant message, so history made the service failure look like an answer.

The importable chatbot workflow has `active: false`, which is expected for an export; it must be imported, configured, and activated in n8n before its production webhook exists. This workspace has no Docker executable or reachable n8n instance, so import/activation, webhook secret acceptance, credential binding, and live Claude replies could not be tested. No valid provider key is available here. The browser screenshot is evidence of the fallback text and existing conversation chips; it is not evidence that a new conversation is created per message. The mobile client sends the selected conversation ID. Historical conversations are preserved.

Anthropic's current model catalog lists `claude-sonnet-5` and `claude-haiku-4-5-20251001` as active IDs. It does not list the requested `claude-sonnet-5-5` or `claude-haiku-5-5` IDs; the existing defaults were retained rather than changing to unverified names. See [Anthropic model lifecycle documentation](https://docs.anthropic.com/en/docs/about-claude/model-deprecations).

## Changes made

- Outage replies are localized in `backend/app/prompts/companion_fallbacks.json`, clearly carry `fallback=true` and `CHAT_UPSTREAM_UNAVAILABLE`, and display a retry action in French/Arabic/English.
- Only actual provider answers and safety responses are stored as assistant messages. Retries carry a stable client message ID and do not add another copy of the user's message.
- Backend logs now report step, error category, HTTP status when available, and duration without message text, identifiers, or other patient data.
- Added protected `GET /api/v1/chat/health` (header `X-Chat-Diagnostics-Token`) and an n8n health webhook. It reports n8n reachability/activation/secret acceptance and Anthropic key/reachability without returning secrets.
- The full trace above includes n8n's patient-scoped internal context request; the LLM receives minimized record facts rather than direct identifiers.

## Checks that require local configuration

Set `ANTHROPIC_API_KEY` in `backend/.env` for direct mode, or import/activate the workflow and configure `CHAT_N8N_WEBHOOK_BASE_URL`, `CHAT_N8N_CHAT_WEBHOOK_URL`, `CHAT_N8N_SHARED_SECRET`, and the corresponding n8n environment values. Also set a separate random `CHAT_DIAGNOSTIC_TOKEN`. Restart FastAPI after configuration. Then run `scripts/check_chat.ps1` with a synthetic patient access token and consented test conversation. The script labels fallback responses as FAIL; a provider-backed response must be observed before calling the live path fixed.

Do not test using real patient text or activate caregiver alerts/summaries against live contacts without consent and clinician review.
