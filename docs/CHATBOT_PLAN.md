# Sakina Psychological Support Chat Plan

## Architecture

- Keep the existing stored medical companion endpoints intact for compatibility, but route Sakina through a new authenticated `POST /api/chat` endpoint. The request contains the current screen session's complete user/assistant history; the backend does not persist it or include it in logs.
- Load Sakina's exact system prompt from `backend/app/prompts/sakina_system.md`. Call Anthropic from FastAPI using `ANTHROPIC_API_KEY` and a configurable `SAKINA_MODEL` defaulting to `claude-sonnet-4-6`; never send credentials to mobile.
- Check multilingual crisis keywords on the mobile screen before sending content to the model, and repeat the check in the backend. Return the locally configured country emergency contacts for a crisis, without calling Anthropic.
- Keep transcript state only in the mounted mobile screen. Show a localized Sakina greeting/disclaimer, message bubbles, typing state, urgent-help contacts, and retryable provider errors with the existing app theme and RTL/i18n setup.

## Files to add or update

- Backend: new Sakina schema and API route, router registration, `SAKINA_MODEL` setting, environment example, exact prompt file, and a short setup note.
- Mobile: replace the stored-history companion screen's data flow with ephemeral Sakina history; add a transient chat API call and translated Sakina title/disclaimer/crisis/retry copy.
- Docs: this plan and backend environment setup instructions.

## Risks and boundaries

- This app sends each full in-memory transcript to Anthropic; provider retention and regional processing must be reviewed before production. HackCure itself will not save or log those messages.
- Client keyword matching improves response speed but cannot identify every crisis. The backend repeats the check; emergency numbers depend on reviewed country configuration.
- Existing persisted companion conversations remain untouched and are not loaded by Sakina. No database migration is needed.
- The endpoint remains patient-authenticated. Provider outages return localized errors with a retry action; no fabricated support answer is stored or presented as an AI reply.
