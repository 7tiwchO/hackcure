# Sakina chat pipeline debug report

## Status

The repeated fallback is explained and surfaced clearly in the code. A real Claude reply is **not verified**: this checkout has no Anthropic API key configured, no running n8n/Docker service, and the exported chat workflow is inactive. The live pipeline cannot succeed until those deployment prerequisites are supplied.

## Root cause evidence

| Layer | Result | Evidence |
|---|---|---|
| A. App → backend | Route contract matches | `mobile/src/services/api/sakina.ts` posts `{ history }` to `/api/chat`; `backend/app/api/sakina.py` exposes authenticated `POST /api/chat`. The screenshot’s fallback bubble matches that endpoint’s outage response. |
| B. Backend → n8n | Was bypassed by the Sakina screen | The previous `backend/app/services/sakina.py` called `_anthropic` directly; it never used the configured n8n webhook. The local `backend/.env` has neither an Anthropic key nor an n8n chat URL/shared secret (values were not read or printed). |
| C. Webhook auth | Not exercised locally | `CHAT_N8N_SHARED_SECRET` is unset in this checkout. No n8n listener is running. |
| D. Workflow | Not running / inactive | No Docker executable or process is available, ports 5678 and 8000 have no listener, and `n8n/chatbot-psychologique.workflow.json` has `active: false`. Therefore there are no live n8n executions or red-node logs to inspect. |
| E. n8n → backend context | Not exercised | No n8n runtime is available. Workflow configuration expects `HACKCURE_API_URL`, `HACKCURE_CHAT_SHARED_SECRET`, and the patient-context authorization token. |
| F. Response contract | Unit-validated | Backend’s shared n8n parser accepts array/object wrappers and validates `reply`, `fallback`, and `error_code`. The Sakina route now returns fallback status and a machine-readable `error_code`. |
| G. Timeouts | Bounded | Mobile’s Sakina request timeout is 70 seconds; backend/n8n timeout is configured through `CHAT_TIMEOUT_SECONDS` (45 seconds by default). |
| H. Triage routing | Keyword-safe locally; full AI triage needs a configured provider | Local crisis keywords still bypass the provider. Direct-provider messages are now triaged before a normal reply. When configured, the n8n workflow routes distress to Claude and bypasses normal reply only for risk/emergency, medication-change, or off-topic labels. |
| I. Failure visibility | Previously too generic | The endpoint returned only a generic connection fallback. The service logs the failing stage, exception category, HTTP status when available, and duration (never message text); the mobile warning now identifies missing provider config, an unavailable n8n workflow, or a network error. |

The absent provider configuration is the concrete reason a normal message cannot produce an AI response in this local checkout: direct Anthropic calls fail before a request because `ANTHROPIC_API_KEY` is empty. The prior broad fallback converted that failure to the same French reply for every message. During a synthetic authenticated request against FastAPI on a temporary test database, the backend emitted only metadata (no message text):

```text
Sakina direct provider is not configured: ANTHROPIC_API_KEY is missing
Sakina n8n route is not configured: CHAT_N8N_CHAT_WEBHOOK_URL is missing
companion upstream failure step=triage category=RuntimeError status=None duration_ms=0
sakina upstream failure step=anthropic category=RuntimeError status=None duration_ms=0
```

The normal message response was `fallback=true`, `error_code=CHAT_PROVIDER_NOT_CONFIGURED`; it returned the existing French retry text. A separate crisis request returned `crisis=true`, `fallback=false`, and Tunisia emergency contacts `190` and `198` without contacting Claude. The temporary API used a new ignored synthetic database; the project's existing databases were not migrated, backed up over, or deleted. There is no past n8n execution log to inspect because no n8n instance is running.

## Changes made

- `backend/app/services/sakina.py`: use the configured n8n chat webhook with the patient's own ID, a stable patient session UUID, signed context token, full bounded/redacted transcript, Sakina system prompt, language, and emergency numbers. Keep direct Anthropic as the explicitly diagnosed compatibility route when n8n is not configured.
- `backend/app/api/sakina.py` and `backend/app/schemas/sakina.py`: look up the authenticated patient profile, triage direct-provider messages before answering, preserve local crisis handling, and expose `fallback` plus `error_code` without storing this route's history.
- `mobile/src/features/companion/CompanionScreen.tsx` and locale files: display a specific localized server/configuration error while keeping retry available.
- `backend/app/main.py`: warn at startup when neither usable provider path is configured or the n8n route is incomplete.
- `backend/app/api/companion.py`: health output no longer says the live Sakina path is ready merely because a separate n8n health webhook accepts its secret. The endpoint marks the unverified n8n chat activation/credential state explicitly.
- Model defaults and the n8n workflow’s model defaults now use `claude-sonnet-5-5` and `claude-haiku-5-5` as requested.
- `scripts/check_chat.ps1`: also probes the exact `/api/chat` endpoint used by the Sakina screen and reports fallback/error code without printing the conversation.

## Not completed / required from deployment owner

1. Add a valid Anthropic key to `backend/.env` as `ANTHROPIC_API_KEY=...` **or** configure `HACKCURE_ANTHROPIC_API_KEY` in the n8n host. Do not paste the key into chat, source control, or the workflow JSON.
2. For the requested n8n path, run n8n, set `CHAT_N8N_CHAT_WEBHOOK_URL` and `CHAT_N8N_SHARED_SECRET` in `backend/.env`, and set matching `HACKCURE_CHAT_SHARED_SECRET`, `HACKCURE_API_URL`, `HACKCURE_ANTHROPIC_API_KEY`, `CHAT_MODEL`, and `TRIAGE_MODEL` in n8n. From Docker, the backend URL must be reachable from the n8n container (often `http://host.docker.internal:8000` for a host-run backend).
3. Import `n8n/chatbot-psychologique.workflow.json`, re-check the environment expressions after import, and activate it. The JSON currently exports inactive. Check that the node credentials/settings survive import and confirm a successful synthetic execution.
4. The chat and health webhooks are nodes in the same imported n8n workflow, so the health webhook confirms whether that workflow is active and accepts the shared secret. It cannot validate the Anthropic credential stored on the n8n host. A successful synthetic message through `/api/chat` is still required as the live check.
5. `CHAT_DIAGNOSTIC_TOKEN`, a synthetic patient access token, and a synthetic consented conversation ID are required to run `scripts/check_chat.ps1`. No secrets or real patient records should be used for this test.

## Verification so far

- TypeScript `tsc --noEmit`: passed after the mobile error-state changes.
- Backend suite: 39 passed. Running pytest inside the Windows sandbox hangs while asyncio creates its required loopback socket pair; the same tests pass when executed outside the sandbox. Two pre-existing test defects were corrected: one checked the wrong French verb form, and one mock did not simulate the database assigning a conversation UUID.
- Mobile `tsc --noEmit`: passed. Expo lint: 0 errors, 30 existing unused/import warnings. Expo web export: passed (1,638 modules bundled).
- The live FastAPI endpoint was verified with a synthetic authenticated patient. No live Claude reply, n8n execution, authenticated browser interaction, or phone result was verified because the provider key is missing and n8n is stopped/inactive.
