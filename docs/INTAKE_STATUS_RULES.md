# Dose intake status rules

The backend `app.services.dose_status.intake_status` function is the single status classifier used by dose lists, dashboard data, dose writes, and adherence totals. Stored/API enum values remain unchanged.

- `TAKEN_ON_TIME`: a recorded `taken_at` falls within the dose's grace interval before or after its prescribed local date/time (default 30 minutes).
- `TAKEN_LATE`: the dose was recorded outside that interval. The existing API has no `TAKEN_EARLY` value, so an unusually early recorded dose also maps to `TAKEN_LATE`; this is a reporting compromise, not dosing guidance.
- `SCHEDULED`: not yet within the pre-dose grace interval.
- `DUE`: inside the ± grace interval and not yet recorded.
- `REMINDING`: the grace interval has passed but the 24-hour forgotten threshold has not.
- `MISSED`: explicitly recorded as missed or still untaken at/after the 24-hour threshold.
- `CANCELLED`: omitted from the dose list and all adherence totals.

Each patient has an IANA timezone (`patients.timezone`), defaulting to `Africa/Tunis`. Date filters and daily/weekly/monthly totals use that timezone. The daily counters are computed from the same patient-scoped day's non-cancelled records as `/api/v1/patients/me/doses/today`; the four counters always sum to `total`. `taken_at` instants are converted to the patient's wall time before comparison with the prescription's local schedule.

Legacy `taken_at` values do not record their original timezone. They are treated as patient-local wall time and are not bulk-shifted. That avoids guessing and keeps the update reversible. If a deployment stored historical values in a different timezone, clinicians should review the effect on legacy on-time/late statistics before using them for care decisions.
