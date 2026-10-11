# Onboarding, intake counters, companion dates, and chatbot plan

## Current state and plan

The app already has a five-step onboarding flow, authenticated patient dose records and adherence aggregates, and a consent-gated companion backed directly by the FastAPI service. The attached screenshots show the final onboarding step and a companion view with repeated absolute dates and an offline banner. There is no Git repository metadata in this workspace, so a new branch or reviewable Git commits cannot be created here; I will keep changes small and document each task clearly.

1. **Onboarding:** verify final-step and skip navigation/persistence. Share one completion action, preserve intermediate steps, and ensure completion routes to a reset auth/app root so Back cannot reopen onboarding. Add focused tests where the app test structure permits.
2. **Intake status/counters:** trace dose list, adherence summary, status transitions, n8n writer and cache refresh. Consolidate backend status classification with explicit grace/forgotten thresholds and patient-local day boundaries. Ensure counters derive from the same day's patient-scoped dose rows, and refresh after dose actions and on screen focus. Avoid schema changes if existing fields suffice.
3. **Companion dates:** audit timestamp creation, serialization, sorting, grouping, and display. Use a shared locale-aware utility with relative French dates and Africa/Tunis day grouping. Preserve existing records; only apply a migration to old rows if their original timezone can be established safely. Otherwise document why historical timestamps cannot be rewritten reliably.
4. **Chatbot/n8n:** validate current workflows against the configured n8n version, audit provider and credentials boundaries, and make the backend remain the auth/consent/safety authority. Create an importable chat workflow only if it can preserve triage-before-response, fail-safe behavior, patient-scoped minimized context, and no raw-message execution retention. Add off-topic and prompt-injection handling and a 30-case eval fixture. Live import/model eval require a reachable n8n instance and provider/search credentials; verify availability and report any external prerequisite rather than claiming a live test.

## Files likely involved

- Mobile routing and onboarding: `mobile/src/features/onboarding/OnboardingScreen.tsx`, `mobile/app/index.tsx`, `mobile/app/_layout.tsx`, auth/store code, locale strings.
- Dose calculations/API: `backend/app/api/patients.py`, `backend/app/api/doses.py`, dose model/schemas/services/tests; `mobile/src/features/adherence/AdherenceScreen.tsx`, relevant queries and focus handling; n8n medication workflow status mapping.
- Companion timestamps and UI: `backend/app/models/companion.py`, companion API/schemas/services/tests; `mobile/src/features/companion/CompanionScreen.tsx`, shared `dateUtils.ts` and locale resources.
- n8n chat integration and documentation: backend companion service/API/config, `n8n/` importable workflow, setup/eval docs, `.env.example`.

## Safety and verification risks

- Prescription timing remains clinician-owned. Intake counters can classify records but cannot change treatment instructions.
- Existing SQLite timestamps are naive. Do not bulk-shift old rows without reliable source timezone evidence and a restorable backup.
- No API keys or live n8n credentials should enter source/workflow JSON. A missing local n8n service may limit live workflow-import testing.
- Scope includes healthcare and crisis handling; mock safety tests do not certify clinical safety. Have a clinician review escalation wording and destination behavior before real-patient use.
