# Treatment tracker UI plan

## Approach

- Add a seven-day adherence strip to each active medication in the Treatment screen, based on the authenticated patient's recorded dose history.
- Add patient-specific stock remaining, refill reminder preference, and low-stock threshold to each prescription item, with an ownership-checked API update.
- Match the reference image's compact weekly status row and stock reminder card while preserving the existing theme, translations, RTL behavior, and clinician-prescribed schedule.

## Files

- Backend: medication model/schema, patient medication API, additive Alembic migration.
- Mobile: treatment tracker component, medication API, medication type, English/French/Arabic labels, Treatment screen integration.

## Safety and data handling

- Never use sample values for a real patient's adherence or stock. Stock starts unknown until the patient enters it.
- Dose times and treatment instructions remain read-only; the new controls only update patient-reported stock and reminder preferences.
- Stock is not automatically decremented because dosage strings do not reliably encode dispensed units (tablets, liquid, injections, etc.). The UI will explain manual stock updates.
- Scope stock reads and writes through the logged-in patient's prescription ownership.
