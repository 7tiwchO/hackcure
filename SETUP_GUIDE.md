# HackCure setup

## Backend

Use Python 3.11+ from `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

The example uses a local SQLite database at `backend/hackcure.db`. Set a unique `SECRET_KEY` before exposing the service. Back up any existing database before applying migrations, then run `alembic upgrade head`. Seed demo data only in a development database with `python -m app.seeds.seed_data`. Start with `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`.

### Windows desktop web test (localhost)

Open two PowerShell windows and keep both running. The API URL in `mobile/.env` should be `http://localhost:8000` for this same-PC test.

PowerShell window 1:

```powershell
Set-Location C:\Users\moham\Desktop\hackcure\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

PowerShell window 2:

```powershell
Set-Location C:\Users\moham\Desktop\hackcure\mobile
npx expo start --web --host localhost --port 8082
```

Open `http://localhost:8082/` on this PC. Check `http://127.0.0.1:8000/health` for `{"status":"ok"...}` if the app reports that its backend is unavailable. Closing either PowerShell window stops that service. These loopback addresses are for the PC browser only; a phone must use the PC's Wi-Fi IPv4 address instead.

If an old browser session receives a 401 and returns to the welcome/sign-in screen, sign in again before testing patient-only pages such as Wellbeing companion.

Last local smoke check (2026-10-11): backend `/health`, Expo web `/`, and the `/companion` deep link each returned HTTP 200 after the patient-timezone migration. `npx expo export --platform web` also completed successfully.

For companion replies through n8n, configure `CHAT_N8N_CHAT_WEBHOOK_URL`, `CHAT_N8N_SHARED_SECRET`, and the n8n environment described in [docs/CHATBOT_N8N_SETUP.md](docs/CHATBOT_N8N_SETUP.md). The active Anthropic API model names documented for this checkout are `claude-sonnet-5` and `claude-haiku-4-5-20251001`; override them with `CHAT_MODEL` and `TRIAGE_MODEL`. These are the closest currently documented model IDs; the requested `claude-sonnet-5-5` and `claude-haiku-5-5` names are not in Anthropic's current model list. If n8n chat is not configured, the backend can use `ANTHROPIC_API_KEY` directly. Without either provider configured, keyword safety routing still runs and the companion returns a brief unavailable-service response. Never put a key in the mobile app or workflow JSON.

Set `CHAT_DEFAULT_COUNTRY` to a country code in `backend/app/safety/emergency_contacts.json`; add and review other country entries locally before using them. Unknown country codes return no guessed number. Configure `CHAT_N8N_WEBHOOK_BASE_URL` and a strong `CHAT_N8N_SHARED_SECRET` only when n8n is reachable from the backend.

## Mobile

Use Node.js 22.13+ and npm from `mobile/`:

```powershell
npm ci
npx tsc --noEmit
npm run lint
npm run check:i18n
npx expo-doctor
npx expo start
```

French is the default app language and fallback. English and Arabic remain selectable in Profile → Language; Arabic enables right-to-left layout. `dateUtils` formats dates and times according to the active language. When adding a screen, add every visible phrase and accessibility label to the corresponding locale resources and run `npm run check:i18n`.

To register from a physical phone, also start the backend (above), connect the phone and PC to the same Wi-Fi, and allow inbound TCP port 8000 through Windows Firewall. Expo Go cannot reach a backend at the PC's `localhost` over mobile data. If Expo is running in tunnel mode, copy `mobile/.env.example` to `mobile/.env`, set `EXPO_PUBLIC_API_URL` to `http://<your-PC-LAN-IPv4>:8000`, then restart Expo with `npx expo start -c`. Find the PC address with `ipconfig` (the Wi-Fi adapter's IPv4 Address). Do not use `127.0.0.1` or `localhost` as the phone's API host.

On Android, Expo Go supports local notifications for testing dose reminders in a foreground or background app, subject to notification permission and the device's battery settings. Expo web does not provide reliable closed-page notifications or guaranteed audible alarms; keep the browser tab open for best-effort reminders. Use an Expo development build to test the final installed-app behavior and interactive notification actions. See the [Expo SDK 57 Notifications documentation](https://docs.expo.dev/versions/v57.0.0/sdk/notifications/).

The patient Home screen includes a 🇹🇳 medical dossier shortcut. It opens records attached to the signed-in patient account. Seeded records are synthetic demo data and belong only to the demo patient; a newly registered patient sees an empty dossier until their own doctor/document workflow adds records.

Log in and open the **Sakina** tab. Chat messages and the visible transcript are kept only in the current mobile screen session; leaving or closing the screen clears them. The patient app sends the complete in-memory transcript to `POST /api/chat`, and the backend calls Anthropic using the secret in `backend/.env`. The urgent-help button and multilingual crisis keyword handling remain available without an Anthropic response.

## n8n

Import the three `n8n/hackcure-companion-*-workflow.json` workflows. Set the n8n environment variables described in [n8n/SETUP_GUIDE.md](n8n/SETUP_GUIDE.md), configure the destination URLs and their shared secrets for the care team, then activate only the schedules you intend to use. Keep n8n execution data saving disabled for these workflows. The escalation webhook sends only a pseudonymous patient reference and safety category; weekly summaries go only to patients who opted into doctor sharing.

The existing document extraction and medication adherence workflows are documented separately in the n8n setup guide. Review their credentials and destination behavior before activating them.
# Sakina psychological support chat

The patient app sends the current screen session's full chat transcript to the authenticated `POST /api/chat` backend endpoint. The transcript stays in mobile memory and is not saved in HackCure's database or application logs. It is sent to Anthropic only from the backend for reply generation. Crisis keywords in English, French, and Arabic are handled locally in the app and checked again by the backend before any model call.

For provider replies, set these values in `backend/.env` and restart FastAPI:

```dotenv
ANTHROPIC_API_KEY=your-anthropic-api-key
SAKINA_MODEL=claude-sonnet-4-6
```

Keep the API key in the backend environment only; never add it to Expo/mobile environment variables. If the key is missing or Anthropic is unreachable, Sakina shows a localized connection message and a retry action. The model-generated chat requires an internet connection. Emergency contacts come from `backend/app/safety/emergency_contacts.json`; review the configured country numbers before deployment.

