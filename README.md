# HackCure - Healthcare Patient Mobile Application & Backend Platform

HackCure is a production-oriented, offline-capable healthcare patient application connected with doctors and pharmacies.

> **Core Architectural Principle:**
> **The doctor's prescription is the single source of truth for the patient's care plan.**
> Patients cannot manually modify medications, dosages, or treatment protocols. When a doctor issues or updates a prescription, the treatment plan, dose schedule, sport regime, and dietary recommendations synchronize automatically.

---

## 🌟 Key Capabilities

1. **Doctor-Prescribed Care Plan Execution**
   - Immutable medication regimens driven strictly by physician prescriptions.
   - Intelligent dose scheduling, reminder countdowns, and real-time state machine: `SCHEDULED` ➔ `DUE` ➔ `REMINDING` ➔ `TAKEN_ON_TIME` / `TAKEN_LATE` / `MISSED`.
   - Adherence analytics with weekly breakdown, percentages, and positive habit streaks.

2. **Integrated Sport & Nutrition Therapy**
   - Physician-assigned aerobic exercise plans with duration and target heart rate guidance.
   - Clinically tailored dietary recommendations, foods to prioritize, and sodium/macro restrictions.

3. **Pharmacy Discovery & Medicine Geolocation**
   - Haversine proximity search for nearby pharmacies.
   - Real-time inventory check with availability flags and unit prices.

4. **Doctor Direct Communication & Telehealth**
   - Real-time conversation threads categorized by medical domain (Medications, Appointments, Sport, Nutrition).
   - In-app appointment scheduling with clinic details and cancellation management.
   - Diagnostic reports, ECG logs, and lipid lab results viewer.

5. **Medical-Grade Safety & Offline Resilience**
   - Offline mutation queue with UUID idempotency keys to eliminate double-dose logging.
   - Prominent clinical emergency disclaimers ("For emergencies, call national emergency medical services").
   - Full Internationalization (English, French, and Arabic) with bidirectional RTL layout mirroring.
   - Comprehensive Dark & Light themes adhering to WCAG contrast standards.

6. **AI Wellbeing Companion**
   - Consent-first emotional support chat grounded in the patient's own prescription and doctor reports.
   - Safety triage, localized emergency contacts, optional care-team sharing, and daily wellbeing check-ins.

---

## 🏗️ Architecture Overview

```
hackcure/
├── backend/
│   ├── app/
│   │   ├── api/             # 11 REST router modules (43 endpoints)
│   │   ├── models/          # 14 SQLAlchemy ORM entities (UUID PKs, proper FKs)
│   │   ├── schemas/         # Pydantic v2 validation models
│   │   ├── seeds/           # Clinical demo data generator
│   │   ├── utils/           # JWT, Bcrypt & cryptographic helpers
│   │   ├── websocket/       # Real-time WebSocket connection manager
│   │   ├── config.py        # Environment & pydantic-settings config
│   │   ├── database.py      # SQLAlchemy 2.0 Async engine (SQLite + Postgres)
│   │   └── main.py          # FastAPI application entrypoint & lifespan
│   ├── tests/               # Pytest async integration test suite
│   ├── Dockerfile
│   └── docker-compose.yml
└── mobile/
    ├── app/                 # Expo Router file-based screens & stacks
    ├── src/
    │   ├── components/      # Reusable UI widgets & healthcare domain cards
    │   ├── features/        # Feature screens (Treatment, Adherence, Doctor, etc.)
    │   ├── hooks/           # Notifications, reminders, network & offline sync hooks
    │   ├── i18n/            # Translations (en, fr, ar) with RTLContext
    │   ├── services/api/    # Axios client with JWT interceptors & API services
    │   ├── store/           # Zustand state (Auth, Offline queue, Settings)
    │   ├── theme/           # Design system tokens (colors, typography, spacing)
    │   └── types/           # Complete TypeScript domain contracts
```

---

## 🚀 Quickstart Guide

For the full environment setup, migration, n8n companion workflows, and verification steps, see [SETUP_GUIDE.md](SETUP_GUIDE.md) and [TESTING_AND_VERIFICATION.md](TESTING_AND_VERIFICATION.md).

### 1. Prerequisites
- **Python**: 3.11+ or 3.12+
- **Node.js**: v20+ or v24+
- **npm**: 10+

---

### 2. Backend Setup & Run

1. Navigate to the backend directory:
   ```powershell
   cd backend
   ```

2. Seed the database with realistic demo patients, cardiologists, and prescriptions:
   ```powershell
   python -m app.seeds.seed_data
   ```

3. Start the FastAPI development server:
   ```powershell
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

   - **Interactive API Documentation (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Alternative ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
   - **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

4. Run Backend Integration Tests:
   ```powershell
   python -m pytest tests/
   ```
   *(All 10 async integration tests execute with zero failures).*

---

### 3. Mobile App Setup & Run

1. Navigate to the mobile directory:
   ```powershell
   cd mobile
   ```

2. Run TypeScript compiler type-check:
   ```powershell
   npx tsc --noEmit
   ```
   *(Zero TypeScript errors).*

3. Start Expo:
   ```powershell
   npx expo start
   ```

4. Press:
   - `a` to run on connected Android emulator / device
   - `w` to run on Web preview
   - `i` to run on iOS simulator (macOS)

---

## 🏥 Lien avec la plateforme hospitalière (Hospital Copilot)

Après son séjour, le patient lie son dossier (pseudonyme `PAT-xxxx` + date de naissance + consentement). L'application synchronise le rapport
et l'ordonnance de sortie par l'API FHIR de l'hôpital, et le **CarePlanAgent** (dans le backend, sans n8n) en tire les rappels de médicaments
(strictement l'ordonnance), un programme d'alimentation, d'activité et d'habitudes (brouillon validé par un médecin), puis suit l'observance.
Sakina s'appuie sur ces données. Sans crédit d'API, tout fonctionne en mode de secours par règles.

- Démarrage : `./scripts/start_with_hospital.ps1` (backend sur le port 8100, Hospital Copilot attendu sur 8000) — compte `zohra@example.com` / `Test123!@#`.
- Démonstration : [docs/DEMO_LIEN_HOPITAL.md](docs/DEMO_LIEN_HOPITAL.md) · État réel et limites : [RAPPORT_APP.md](RAPPORT_APP.md) · Décisions : [DECISIONS_APP.md](DECISIONS_APP.md)

---

## 🔑 Demo Credentials

| Role | Email | Password | Details |
|---|---|---|---|
| **Patient** | `mohamed@example.com` | `Test123!@#` | Mohamed Trabelsi (Hypertension care plan, 3 medications, adherence history) |
| **Doctor** | `dr.ahmed@hackcure.org` | `Test123!@#` | Dr. Ahmed Ben Ali (Cardiologist, clinic details, prescribing physician) |
| **Doctor** | `dr.leila@hackcure.org` | `Test123!@#` | Dr. Leila Mansouri (Endocrinologist & Nutritionist) |

---

## 🔒 Security & Medical Disclaimers
- **Data Isolation**: All patient endpoints strictly filter queries by the authenticated user's ID.
- **Idempotency**: Doses and offline sync events include client-generated UUID idempotency keys to ensure zero duplicate logs during network reconnections.
- **Emergency Protection**: The application is not an emergency triage tool. Any critical distress instructs the patient immediately to call emergency medical numbers.
