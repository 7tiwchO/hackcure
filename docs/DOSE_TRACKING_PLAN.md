# Dose tracking and local web plan

## Current behavior and defects

- Dose cards already offer a take action and dose history/adherence endpoints already exist.
- The mobile client sends non-UUID idempotency keys although the API schema requires UUID; dose confirmation can fail validation.
- The backend idempotency lookup occurs before dose ownership validation and can return another patient's dose if a key is reused.
- Timezone-aware mobile timestamps are subtracted from timezone-naive scheduled times, which can raise a server error.
- Dose reminders are not consistently scheduled when a patient opens the medication list; the existing rebuild cancels every app notification, not just medication alarms.
- Expo SDK 57 supports local notifications in Expo Go on Android, subject to notification permission and device settings. Expo web cannot guarantee notifications or sound when the tab is closed. Validate final installed-app behavior in a development build.
- The previous web server ran in an isolated environment and Edge timed out. Restart it outside the sandbox, bound to localhost only.

## Plan

1. Keep `scheduled_date` and `scheduled_time` as the clinician-prescribed source of truth. Do not expose an edit that silently changes a treatment instruction. Show the date/time beside each pill and explain that schedule corrections should go through the care team.
2. Make take-dose idempotency use a valid stable UUID and validate dose ownership before idempotency returns any row. Normalize aware timestamps to the server's local schedule timezone before classifying on-time/late.
3. Schedule/cancel per-dose local reminders when the medication list loads and when doses change. Keep sound enabled, respect permissions, avoid cancelling unrelated notifications, and keep the taken action connected to the authenticated backend. Invalidate today's doses, dashboard, adherence, and history after success; show errors and retry paths.
4. Add backend tests for aware timestamps, patient isolation with reused idempotency keys, and on-time/late recording. Run backend tests, mobile typecheck/lint/i18n checks, Expo web export, and verify local HTTP response from the desktop host.

## Risks and constraints

- A patient-configurable reminder time is distinct from the prescribed dosing time. This pass keeps alarms aligned with the prescription and does not alter prescribed dates/times.
- Audible local notification behavior depends on platform support, OS permission, notification-channel settings, and device battery policy. Expo web cannot guarantee closed-tab notifications or sound.
- This workspace has no `.git` metadata, so changes cannot be committed or placed on a feature branch here.
