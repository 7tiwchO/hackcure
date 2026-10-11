# Medical dossier shortcut plan

## Goal

Give every patient a clear, Tunisian-marked entry point to their own medical dossier while preserving the existing doctor-managed records and patient authorization model.

## Architecture

- Add a medical-folder quick action to the authenticated patient Home dashboard. Use the existing Expo Router `/medical-records` route and existing `GET /api/v1/medical-records` API.
- Keep record fetching server-scoped to the authenticated patient. Include the authenticated user ID in client query keys so cached records cannot be reused across patient accounts on a shared device.
- Use the existing French, English, and Arabic labels and RTL behavior. Add a small Tunisia flag marker to the folder shortcut.
- Continue using the seeded synthetic records only for the seeded demo patient; do not create fictional clinical records for newly registered patients. A real patient sees an empty dossier until their doctor or document workflow attaches records to that patient's ID.

## Files to change

- `mobile/src/features/home/HomeScreen.tsx`: add the dossier shortcut and link it to the existing records list.
- `mobile/src/features/medical-records/MedicalRecordListScreen.tsx`: scope the query cache to the logged-in user.
- `mobile/src/features/medical-records/MedicalRecordDetailScreen.tsx`: scope detail cache to the logged-in user.
- `scripts/check_all.ps1`: run integration tests against a disposable database copy and add a fresh-database migration check.
- `scripts/start_dev.ps1` and `scripts/start_web.ps1`: use `backend/.venv` and stop overwriting `mobile/.env`.
- `docs/AUDIT.md`: record newly found setup risks and verification results.
- `docs/MEDICAL_RECORDS_PLAN.md`: preserve this implementation plan.

## Risks and safeguards

- Medical data is sensitive: do not add a client-supplied patient ID to the records request or weaken backend checks. The API already derives the patient from the authenticated user and filters detail requests by that patient's ID.
- Demo records are synthetic: keep them limited to the existing demo seeder/account and never auto-populate a newly registered account with made-up diagnoses or results.
- No schema or migration change is needed. This avoids touching the existing SQLite patient database.
- The existing full-check script can mutate its configured DB, so all test and migration checks must point to disposable copies/files.
- Launch scripts must preserve developer `.env` values and use the backend virtual environment that contains the pinned dependencies.

## Verification

- Run mobile TypeScript and lint checks, and run the backend test suite against a temporary copy of the seeded database as required by `TESTING_AND_VERIFICATION.md`.
- Confirm the seeded medical records remain linked to the seeded patient's ID and the API routes continue to enforce ownership.
