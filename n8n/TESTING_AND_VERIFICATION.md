# HackCure — End-to-End Testing & Verification Guide

Companion setup and workflow verification are described in the root [TESTING_AND_VERIFICATION.md](../TESTING_AND_VERIFICATION.md) and [SETUP_GUIDE.md](../SETUP_GUIDE.md).

## 1. Automated Test Suite Status

### Backend Integration Tests (11/11 passing)
Run in `backend/`:
```bash
python -m pytest tests/ -v
```
**Results:**
- `test_login_success`: PASSED
- `test_patient_profile`: PASSED
- `test_get_dashboard`: PASSED
- `test_get_prescriptions`: PASSED
- `test_get_today_doses_and_take_dose`: PASSED
- `test_get_conversations_and_send_message`: PASSED
- `test_get_appointments`: PASSED
- `test_automation_report_draft_and_apply`: PASSED (Report extraction draft, Prescription extraction draft, drafts query, atomic apply, dose generation, sport/nutrition plans generation, audit log generation)

### Mobile App TypeCheck
Run in `mobile/`:
```bash
npx tsc --noEmit
```
**Result:** 0 errors (clean compilation).

---

## 2. Testing the n8n 2-Document Flow

### Step A: Start Backend Server
```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Step B: Import Workflow in n8n
1. Open n8n at `http://localhost:5678`.
2. Click **Add workflow** → **Import from file** → select `n8n/hackcure-document-extraction-workflow.json`.
3. Set your Anthropic API Key in n8n credentials (`Anthropic API Key`).
4. Activate the workflow.

### Step C: Test Upload Webhook (Doctor Report + Prescription)
Send a sample doctor report and prescription:
```bash
curl -X POST http://localhost:5678/webhook/hackcure-upload \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "REPLACE_WITH_PATIENT_UUID",
    "rapport_base64": "Rapport Médical: Patient présentant une hypertension artérielle stade 1. Traitement: Amlodipine 5mg 1 comprimé le matin. Activité physique: Marche rapide 4 fois par semaine, éviter les charges lourdes. Alimentation: Réduire le sel <2g/j, privilégier légumes et poissons.",
    "ordonnance_base64": "Ordonnance: Amlodipine 5mg boîte de 30 comprimés. 1 cp par jour le matin pendant 90 jours."
  }'
```

**Expected Result:**
- Returns JSON with `status: "DRAFT"`, extracted parameters, and confidence scores.
- App displays a banner: `"Nouveau traitement détecté depuis vos documents (Brouillon)"`.

### Step D: Confirm and Apply the Draft
From the mobile app (or via webhook):
- Tap the `"Confirmer et Appliquer le traitement"` button in **"Mon traitement"**.
- Atomically:
  1. Archives the previous prescription and treatment summary.
  2. Sets the new care plan as `is_current: true`.
  3. Regenerates all daily doses with exact times.
  4. Flushes and reschedules all reminders with sound and 30-min repeat logic.
  5. Updates "Sport", "Nutrition", and "Pharmacie" sections immediately.

---

## 3. Physical Device Verification (Expo Go)

1. Make sure your PC and Android phone are on the same Wi-Fi.
2. In `backend/`: start uvicorn on `0.0.0.0:8000`.
3. In `mobile/`: start Expo:
   ```bash
   npx expo start -c
   ```
4. Scan the QR code with Expo Go on your Android phone.
5. Log in with `mohamedallagui22@gmail.com`.
6. Verify:
   - **Mon traitement**: Displays doctor report summary, clinical diagnosis, goals, warnings, next appointment date, and active medications.
   - **Sport**: Displays recommended activities (green tags), forbidden activities (red tags), frequency, and medical restrictions.
   - **Nutrition**: Displays foods to prioritize, foods to limit, calories & hydration targets, and dietary advice.
   - **Pharmacie**: Displays real partner pharmacy stock, distance, prices in TND, and prescribed quantities.
   - **Médicaments**: Displays doses scheduled today. Tapping "I TOOK IT" immediately records the dose and kills repeating alarms. Tap "Historique & Suivi des prises" to view all historical takes and missed doses with timestamps.
