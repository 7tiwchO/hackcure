# Testing and verification

## Backend

Run in `backend/`:

```powershell
python -m pytest tests/ -q
```

The tests cover the existing API plus medical-record patient isolation (a patient cannot list or fetch another patient's record), companion patient isolation, triage routing, keyword fallback, per-user rate limits, prompt-context PII redaction, and a 30-case multilingual eval fixture in `tests/evals/companion_triage.json`. Use a temporary copy of the database for the legacy integration suite; several existing tests update doses and create records.

Check a fresh schema on a new database:

```powershell
$env:DATABASE_URL = 'sqlite+aiosqlite:///C:/Temp/hackcure-migration-check.db'
alembic upgrade head
```

Do not point this check at the existing patient database. Back up an existing database before applying migrations there.

## Mobile

Run in `mobile/`:

```powershell
npx tsc --noEmit
npm run lint
npm run check:i18n
npx expo export --platform android --output-dir .expo/i18n-bundle
npx expo start --offline
```

The Expo lint command reports existing warnings in unrelated screens; fix lint errors before accepting changes. `check:i18n` scans app/src TypeScript for hardcoded visible labels and unresolved French keys. Test manually at 320 px, 360 px, 390 px, 412 px, and tablet widths; include landscape, increased system font, long medical names/instructions, forms with the keyboard open, French dates, Arabic RTL, and screen reader navigation. Confirm scroll, chips, buttons, and bottom tabs remain reachable without clipping.

### French and responsive UI results (2026-10-10)

- `npm run check:i18n`: passed; no hardcoded visible UI strings or missing French keys in 132 TypeScript files.
- `npx tsc --noEmit`: passed.
- `npm run lint`: passed with 0 errors and 35 warnings (unused imports/variables and existing import-style warnings).
- `expo export --platform android`: passed; Metro bundled 2,004 modules. On this Windows environment, the Hermes temporary output had to be redirected to `mobile/.expo/i18n-verification` due restricted system temp permissions.
- `npx expo-doctor`: passed; 21/21 checks passed after network access became available for the CLI package.
- Physical-device/simulator layout and accessibility checks remain manual; use the checklist below.

Manual French/responsive checklist:

1. Welcome and onboarding: French text, language switch, long subtitle and buttons at 320 px/large text.
2. Sign in, registration, password reset: French validation/server/offline errors, keyboard does not cover focused input or submit button.
3. Home: cards wrap, dossier shortcut and tabs remain visible, patient-specific names are preserved.
4. Treatment, prescription, medication detail, adherence and dose history: status labels, French dates/times, long drug names and doctor instructions wrap without truncation; clinical values remain unchanged.
5. Pharmacy, nutrition and activity: long availability and recommendation copy wraps, filters and empty/error states remain usable.
6. Doctor chat, appointments, medical records and notifications: message/record content remains readable; actions and accessibility labels are present.
7. Companion: consent, sharing control, urgent-help action, mood, quick replies and keyboard input; test offline/errors and scroll history.
8. Profile, language and appearance settings: selected state, back navigation, translated descriptions and larger text.

## Dose tracking verification (2026-10-10)

- Backend suite: `24 passed` using a temporary copy of the SQLite database; the project's `backend/hackcure.db` was not used by that run.
- Dose API regression: timezone-aware local `taken_at` is classified correctly and idempotency replay across patients is rejected (`404`).
- Mobile: `npx tsc --noEmit`, `npm run lint` (0 errors; existing warnings), and `npm run check:i18n` passed.
- Local web/API: Expo web returned HTTP 200 at `http://localhost:8082/`, and FastAPI returned HTTP 200 from `http://127.0.0.1:8000/health`; Metro bundled the app entry successfully. Both localhost servers are running now. This confirms the web page and API health endpoint serve; patient login and live dose flows still require a valid account.
- Manual device check: allow notification permission, set an upcoming prescribed dose, confirm its displayed date/time and sound reminder, mark it taken, and confirm the backend history/adherence count updates. Verify late-dose status by marking a dose after its scheduled time. Expo web cannot guarantee audible reminders after the tab closes.
9. Repeat in French and Arabic; verify RTL in Arabic, date locale, landscape, 390/412 px phones, ≥768 px tablet, 150% system font, and screen reader navigation.

## n8n

Validate each workflow JSON parses, import into a non-production n8n instance, and confirm that credentials and environment variables resolve before activation. Trigger escalation and weekly summary with synthetic data and confirm the destination is configured. Check n8n settings retain neither successful nor failed execution payloads for these workflows.

The 30-case eval file is a review set, not a clinical safety certification. Run model-based triage evaluations against the configured provider before deployment and review crisis flows with clinicians.

## Companion, patient-local dose status, and local web verification (2026-10-11)

- Backend suite: `32 passed` against a copied SQLite database after migrating that copy; the main patient database is not used by the tests.
- Schema: fresh Alembic migration succeeded on a new SQLite database. Before migrating the configured patient database, a SQLite online backup was created and integrity-checked. Migration `0002_patient_timezone` succeeded; the database reports `PRAGMA integrity_check=ok` and `patients.timezone` is present.
- Mobile: `npx tsc --noEmit` passed; `npm run check:i18n` passed for 132 TypeScript files; `npm run lint` completed with 0 errors and 31 existing warnings in unrelated screens/utilities.
- Expo Web production export: `npx expo export --platform web --output-dir .expo/verification-web` passed; Metro bundled 1,617 modules and emitted both web bundles.
- Python: backend `compileall` passed. All six n8n workflow JSON files parsed, node connection references resolved, and Code node JavaScript syntax checks passed.
- Localhost: FastAPI `http://127.0.0.1:8000/health`, Expo Web `http://localhost:8082/`, and the `/companion` deep link returned HTTP 200. Visual browser inspection found the existing patient session had expired (`401` on companion consent/contact requests); after reload the app correctly displayed sign-in. Log in again to validate authenticated companion consent/chat. No message was submitted. Native sound/notifications, and responsive/accessibility behavior still need manual verification.
- The first migration-aware test attempt used an old database copy and correctly failed because that copy lacked `patients.timezone`; after upgrading the disposable copy, all tests passed. No project data was removed.
- Live n8n import/provider-backed evaluation could not be performed: no n8n instance or Docker executable is available in this environment. See [chatbot n8n setup](docs/CHATBOT_N8N_SETUP.md).
- No branch or fix commits were created because this workspace has no `.git` metadata. The source database and a dated pre-migration SQLite backup remain local; database files are ignored by `.gitignore`.
