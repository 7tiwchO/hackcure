"""
Lien avec Hospital Copilot, CarePlanAgent, abonnement et Sakina fondée sur le dossier.
L'hôpital est simulé par un transport HTTP local (aucun réseau) qui sert un Bundle FHIR au format de la plateforme.
"""
import base64
import uuid
from datetime import date, datetime, time, timedelta

import httpx
import pytest
from sqlalchemy import delete, select

from app.agents import care_plan_agent as agent
from app.config import settings
from app.database import AsyncSessionLocal
from app.integrations import hospital_copilot as hc
from app.models.audit_log import AuditLog
from app.models.dose import DoseStatus, MedicationDose
from app.models.hospital_link import AgentRun, CareProgram, HospitalLink, Subscription
from app.models.medication import PrescriptionItem
from app.models.notification import Notification
from app.models.nutrition import NutritionPlan, NutritionPlanStatus
from app.models.patient import Gender, Patient
from app.models.prescription import Prescription
from app.models.user import User, UserRole
from app.seeds.seed_hospital_demo import DEMO_EMAIL, DEMO_PASSWORD, demo_birth_date, seed
from app.services import hospital_sync
from app.utils.security import create_access_token, get_password_hash

pytestmark = pytest.mark.asyncio
REPORT = ("Compte rendu de sortie. PAT-0004, 75 ans, opérée d'une prothèse totale de hanche droite après fracture du col du fémur. Anémie post-opératoire modérée. "
          "Suites simples. Marche avec déambulateur, appui complet autorisé. Régime riche en protéines et en fer. Surveillance de la cicatrice et contrôle de la NFS dans 10 jours. "
          "Éviter de croiser les jambes pendant 6 semaines. Kinésithérapie 3 fois par semaine.")


def medreq(mid, name, category, dose_text, times=None, frequency=None, days=None, value=None, unit=None, status="active"):
    repeat = {}
    if times:
        repeat["timeOfDay"] = [t + ":00" for t in times]
    if frequency:
        repeat.update(frequency=frequency, period=1, periodUnit="d")
    if days:
        repeat["boundsDuration"] = {"value": days, "unit": "jour", "system": "http://unitsofmeasure.org", "code": "d"}
    dosage = {"text": dose_text, "route": {"text": "voie orale"}}
    if repeat:
        dosage["timing"] = {"repeat": repeat}
    if value:
        dosage["doseAndRate"] = [{"doseQuantity": {"value": value, "unit": unit}}]
    return {"resourceType": "MedicationRequest", "id": mid, "status": status, "intent": "order",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/medicationrequest-category", "code": category}]}],
            "medicationCodeableConcept": {"text": name}, "subject": {"reference": "Patient/PAT-0004"}, "authoredOn": "2026-10-10T09:00:00+00:00",
            "requester": {"display": "Dr Nour Khelifi"}, "dosageInstruction": [dosage]}


def bundle(extra_meds=()):
    patient = {"resourceType": "Patient", "id": "PAT-0004", "identifier": [{"system": "urn:hackcure:pseudonym", "value": "PAT-0004"}], "gender": "female",
               "birthDate": demo_birth_date().isoformat(), "name": [{"family": "Chaabane", "given": ["Zohra"]}], "telecom": [{"value": "+216 00 000 000"}]}
    resources = [
        patient,
        {"resourceType": "Condition", "id": "c1", "code": {"text": "Fracture du col du fémur opérée (prothèse totale de hanche)"}, "category": [{"coding": [{"code": "problem-list-item"}]}]},
        {"resourceType": "Condition", "id": "c2", "code": {"text": "Anémie post-opératoire"}},
        {"resourceType": "AllergyIntolerance", "id": "a1", "code": {"text": "AINS"}},
        {"resourceType": "AllergyIntolerance", "id": "a2", "code": {"text": "aspirine"}},
        {"resourceType": "Encounter", "id": "e1", "status": "in-progress", "period": {"start": "2026-10-06T10:00:00+00:00"}, "reasonCode": [{"text": "Suites de prothèse de hanche"}]},
        {"resourceType": "Observation", "id": "o1", "status": "final", "category": [{"coding": [{"code": "vital-signs"}]}], "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]}, "valueQuantity": {"value": 76, "unit": "/min"}},
        {"resourceType": "Observation", "id": "o2", "status": "final", "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9"}]},
         "component": [{"code": {"coding": [{"code": "8480-6"}]}, "valueQuantity": {"value": 118}}, {"code": {"coding": [{"code": "8462-4"}]}, "valueQuantity": {"value": 72}}]},
        medreq("m1", "Paracétamol (Doliprane)", "discharge", "1 g · voie orale · 3 fois par jour · pendant 7 j", frequency=3, days=7, value=1, unit="g"),
        medreq("m2", "Énoxaparine (Lovenox)", "discharge", "4000 UI · sous-cutanée · à 20:00 · pendant 30 j", times=["20:00"], days=30),
        medreq("m3", "Fer (Tardyferon)", "discharge", "80 mg · voie orale"),
        medreq("m4", "Morphine", "inpatient", "5 mg · IV · à 08:00", times=["08:00"]),
        *extra_meds,
        {"resourceType": "DocumentReference", "id": "doc-report-1", "status": "current", "type": {"coding": [{"system": "http://loinc.org", "code": "18842-5"}], "text": "Rapport de sortie"},
         "subject": {"reference": "Patient/PAT-0004"}, "date": "2026-10-10T08:30:00+00:00", "author": [{"display": "Dr Nour Khelifi"}],
         "content": [{"attachment": {"contentType": "text/plain; charset=utf-8", "language": "fr", "title": "Compte rendu de sortie", "data": base64.b64encode(REPORT.encode()).decode()}}]},
    ]
    return {"resourceType": "Bundle", "type": "searchset", "total": len(resources), "entry": [{"fullUrl": f"x/{r['id']}", "resource": r} for r in resources]}


class FakeHospital:
    """Remplace la plateforme hospitalière : mêmes routes FHIR, même contrôle du jeton."""

    def __init__(self):
        self.online, self.calls, self.extra = True, [], []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url.path)
        if not self.online:
            raise httpx.ConnectError("hôpital arrêté")
        if request.headers.get("authorization") != "Bearer jeton-de-test":
            return httpx.Response(401, json={"detail": "Authentification requise"})
        b = bundle(self.extra)
        if request.url.path == "/fhir/Patient/PAT-0004":
            return httpx.Response(200, json=b["entry"][0]["resource"])
        if request.url.path == "/fhir/Patient/PAT-0004/$everything":
            return httpx.Response(200, json=b)
        return httpx.Response(404, json={"resourceType": "OperationOutcome", "issue": [{"diagnostics": "Patient introuvable"}]})


@pytest.fixture
def hospital(monkeypatch):
    fake = FakeHospital()
    monkeypatch.setattr(settings, "HOSPITAL_COPILOT_SERVICE_TOKEN", "jeton-de-test")
    monkeypatch.setattr(settings, "HOSPITAL_COPILOT_RETRIES", 1)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "DEMO_AUTO_APPLY", False)
    real = hc.HospitalCopilotClient

    def factory(*a, **k):
        k.setdefault("transport", httpx.MockTransport(fake.handler))
        return real(*a, **k)

    monkeypatch.setattr(hc, "HospitalCopilotClient", factory)
    return fake


async def zohra(client):
    await seed()
    res = await client.post("/api/v1/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert res.status_code == 200, res.text
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    await client.delete("/api/hospital-link", headers=headers)        # état de départ : non liée
    async with AsyncSessionLocal() as db:
        patient = (await db.execute(select(Patient).join(User, User.id == Patient.user_id).where(User.email == DEMO_EMAIL))).scalar_one()
        await db.execute(delete(Notification).where(Notification.user_id == patient.user_id))
        await db.commit()
    return headers, patient


# ── fonctions pures ──────────────────────────────────────────────────────────
async def test_bundle_is_sanitized_and_parsed_without_inventing_anything():
    clean = hc.sanitize_bundle(bundle())
    assert "name" not in clean["entry"][0]["resource"] and "telecom" not in clean["entry"][0]["resource"]      # aucun nom conservé
    parsed = hc.parse_bundle(clean)
    assert parsed["patient"]["pseudonym"] == "PAT-0004" and parsed["patient"]["age"] in (74, 75) and parsed["allergies"] == ["AINS", "aspirine"]
    assert parsed["vitals"] == {"hr": 76, "sys": 118, "dia": 72} and parsed["documents"][0]["kind"] == "discharge" and "déambulateur" in parsed["documents"][0]["text"]
    old = {"resourceType": "DocumentReference", "id": "doc-old", "type": {"coding": [{"code": "18842-5"}]}, "date": "2019-03-02T10:00:00+00:00", "author": [{"display": "Dr Ancien"}],
           "content": [{"attachment": {"data": base64.b64encode("Séjour de 2019 : régime sans sel strict, repos complet.".encode()).decode()}}]}
    with_old = bundle()
    with_old["entry"].append({"resource": old})
    p2 = hc.parse_bundle(with_old)
    assert [d["id"] for d in hc.stay_documents(p2)] == ["doc-report-1"]                                      # un ancien séjour ne donne pas de consigne
    assert not any("2019" in c or "sans sel" in c for c in agent.extract_parameters(p2)["doctor_instructions"])
    meds, origin = hc.discharge_medications(parsed)
    assert origin == "ordonnance de sortie" and [m["name"] for m in meds] == ["Paracétamol (Doliprane)", "Énoxaparine (Lovenox)", "Fer (Tardyferon)"]   # l'ordonnance hospitalière n'est pas reprise
    para, lovenox, fer = meds
    assert para["dose"] == "1 g" and para["per_day"] == 3 and para["times"] == ["08:00", "14:00", "20:00"] and para["times_source"] == "convention" and para["duration_days"] == 7
    assert lovenox["times"] == ["20:00"] and lovenox["times_source"] == "ordonnance" and lovenox["duration_days"] == 30
    assert fer["times"] == [] and fer["per_day"] is None and fer["times_source"] == "absent"                 # ni horaire ni fréquence : rien n'est inventé
    payload, warnings = agent.medication_payload(uuid.uuid4(), parsed, today=date(2026, 10, 11))
    assert [m["heures_prises"] for m in payload["medicaments"]] == [["08:00", "14:00", "20:00"], ["20:00"], []]
    assert any("Fer" in w and "aucun rappel" in w for w in warnings) and payload["doctor_name"] == "Dr Nour Khelifi"


async def test_rules_and_guardrails_respect_pathology_allergies_and_contraindications():
    params = agent.extract_parameters(hc.parse_bundle(bundle()))
    assert params["flags"]["ortho"] and params["flags"]["anemia"] and params["flags"]["anticoagulant"] and not params["flags"]["diabetes"]
    assert any("croiser les jambes" in c for c in params["doctor_instructions"]) and agent.source_line(params) == "issu de l'ordonnance de sortie du Dr Nour Khelifi du 10/10/2026"
    plan = agent.rule_based_plan(params)
    assert plan["activity"]["intensity"] == "LIGHT" and any("course" in c for c in plan["activity"]["contraindications"])
    assert any("fer" in f for f in plan["nutrition"]["recommended_foods"]) and 0 < plan["nutrition"]["confidence"] <= 1
    assert any(h["key"] == "bleeding" for h in plan["habits"]) and any(h["key"].startswith("doctor_") and h["confidence"] == 0.95 for h in plan["habits"])
    # insuffisance cardiaque + diabète + allergie alimentaire : un plan « LLM » fautif est corrigé par les garde-fous
    cardiac = {"age": 68, "allergies": ["arachide"], "flags": {**{k: False for k in agent.FLAGS}, "heart_failure": True, "diabetes": True, "anticoagulant": False}, "medications": [], "doctor_instructions": []}
    bad = {"nutrition": {"plan_type": "Hyperprotéiné", "recommended_foods": ["beurre de cacahuète", "légumes"], "foods_to_avoid": [], "hydration_ml_daily": 3000, "confidence": 7},
           "activity": {"activity_name": "Course à pied", "activity_type": "RUNNING", "intensity": "VIGOROUS", "duration_minutes": 90, "contraindications": []},
           "habits": [{"key": "x", "category": "other", "title": "Astuce", "detail": "Vous pouvez doubler votre dose de médicament si besoin."}]}
    fixed, fixes = agent.apply_guardrails(bad, cardiac)
    nut, act = fixed["nutrition"], fixed["activity"]
    assert "beurre de cacahuète" not in nut["recommended_foods"] and "hyposod" in nut["plan_type"].lower() and "glucid" in nut["plan_type"].lower()
    assert nut["hydration_ml_daily"] == 1500 and any("sel" in f for f in nut["foods_to_avoid"]) and any("sucre" in f for f in nut["foods_to_avoid"]) and nut["confidence"] == 1.0
    assert act["intensity"] == "LIGHT" and act["activity_type"] == "WALKING" and act["duration_minutes"] <= 30 and any("efforts intenses" in c for c in act["contraindications"])
    assert not any("doubler" in h["detail"] for h in fixed["habits"]) and any(h["key"] == "weight" for h in fixed["habits"]) and len(fixes) >= 6


async def test_adherence_flags_three_missed_doses_of_a_critical_medicine():
    now = datetime(2026, 10, 11, 21, 0)
    rows = [("Énoxaparine (Lovenox)", date(2026, 10, d), time(20, 0), DoseStatus.MISSED) for d in (8, 9, 10)]
    rows += [("Paracétamol", date(2026, 10, 10), time(8, 0), DoseStatus.TAKEN_ON_TIME), ("Paracétamol", date(2026, 10, 11), time(8, 0), DoseStatus.SCHEDULED)]
    adh = agent.adherence_from_doses(rows, now)
    assert adh["critical_missed"] == ["Énoxaparine (Lovenox)"] and adh["missed_streak"] == 3 and adh["due_7d"] == 5 and adh["taken_7d"] == 1 and "oubliées" in adh["message"]
    assert agent.adherence_from_doses([("Vitamine C", date(2026, 10, d), time(8, 0), DoseStatus.MISSED) for d in (8, 9, 10)], now)["critical_missed"] == []
    assert agent.adherence_from_doses([], now)["rate_7d"] is None


# ── parcours complet ─────────────────────────────────────────────────────────
async def test_link_sync_agent_program_offline_and_validation(client, hospital):
    headers, patient = await zohra(client)
    wrong = {"pseudonym": "PAT-0004", "date_of_birth": "1950-01-01", "consent": True}
    assert (await client.post("/api/hospital-link", json={**wrong, "consent": False}, headers=headers)).status_code == 400              # consentement explicite
    assert (await client.post("/api/hospital-link", json=wrong, headers=headers)).status_code == 404                                     # date de naissance fausse
    assert (await client.post("/api/hospital-link", json={**wrong, "pseudonym": "XYZ-12"}, headers=headers)).status_code == 400
    res = await client.post("/api/hospital-link", json={"pseudonym": "pat-0004", "date_of_birth": demo_birth_date().isoformat(), "consent": True}, headers=headers)
    assert res.status_code == 200, res.text
    st = res.json()
    assert st["linked"] and st["pseudonym"] == "PAT-0004" and st["last_sync_status"] == "ok" and st["consent_at"] and st["subscription_active"]
    kinds = {d["type"] for d in st["documents"]}
    assert {"PRESCRIPTION", "DOCTOR_REPORT", "MEDICAL_RECORD"} <= kinds and any("Rapport de sortie" in d["title"] for d in st["documents"])
    run = st["last_agent_run"]
    assert run["mode"] == "rules" and run["status"] == "ok" and [s["name"] for s in run["steps"]] == ["extraction", "medicaments", "programme", "validation", "suivi"]
    assert "sans LLM" in run["steps"][1]["detail"] and "mode de secours" in run["steps"][2]["detail"] and "brouillon" in run["steps"][3]["detail"]

    async with AsyncSessionLocal() as db:
        link = (await db.execute(select(HospitalLink).where(HospitalLink.patient_id == patient.id))).scalar_one()
        assert "Chaabane" not in str(link.cached_bundle) and "Zohra" not in str(link.cached_bundle)                                        # aucun nom stocké
        items = (await db.execute(select(PrescriptionItem).join(Prescription).where(Prescription.patient_id == patient.id, Prescription.is_current.is_(True)))).scalars().all()
        by = {i.medication_name: i for i in items}
        assert set(by) == {"Paracétamol (Doliprane)", "Énoxaparine (Lovenox)", "Fer (Tardyferon)"}
        assert by["Paracétamol (Doliprane)"].dosage == "1 g" and by["Énoxaparine (Lovenox)"].scheduled_times == ["20:00"]                 # strictement l'ordonnance
        doses = (await db.execute(select(MedicationDose).where(MedicationDose.prescription_item_id == by["Énoxaparine (Lovenox)"].id))).scalars().all()
        assert len(doses) == 31 and {d.scheduled_time for d in doses} == {time(20, 0)}
        assert not (await db.execute(select(MedicationDose).where(MedicationDose.prescription_item_id == by["Fer (Tardyferon)"].id))).scalars().all()
        assert (await db.execute(select(AuditLog).where(AuditLog.patient_id == patient.id, AuditLog.action == "CARE_AGENT_RUN"))).scalars().first()

    prog = (await client.get("/api/care-program", headers=headers)).json()
    assert prog["mode"] == "rules" and prog["fallback"] is True and prog["validation"] == {"status": "draft", "auto_applied": False, "label": agent.DRAFT_LABEL, "validated_by": None}
    assert prog["source"] == "issu de l'ordonnance de sortie du Dr Nour Khelifi du 10/10/2026" and prog["medications"]["count"] == 3 and prog["medications"]["next_dose"]
    for block in (prog["nutrition"], prog["activity"], *prog["habits"]):
        assert block["source"] and 0 <= block["confidence"] <= 1
    assert prog["activity"]["intensity"] == "LIGHT" and len(prog["habits"]) >= 5

    # nouvelle synchronisation sans changement : rien n'est refait
    again = (await client.post("/api/hospital-link/sync", headers=headers)).json()
    assert [s["status"] for s in again["last_agent_run"]["steps"][1:3]] == ["skipped", "skipped"]
    # nouvelle ordonnance côté hôpital : le calendrier est refait
    hospital.extra = [medreq("m9", "Calcium vitamine D", "discharge", "1 cp · voie orale · à 12:00", times=["12:00"], days=30)]
    changed = (await client.post("/api/hospital-link/sync", headers=headers)).json()
    assert changed["last_agent_run"]["steps"][1]["status"] == "ok" and "4 médicament(s)" in changed["last_agent_run"]["steps"][1]["detail"]
    # hôpital injoignable : la dernière synchronisation reste disponible
    hospital.online = False
    off = await client.post("/api/hospital-link/sync", headers=headers)
    assert off.status_code == 200 and off.json()["last_sync_status"] == "offline" and off.json()["last_sync_at"] and len(off.json()["documents"]) >= 3
    assert (await client.get("/api/care-program", headers=headers)).status_code == 200
    runs = (await client.get("/api/agent/runs?limit=5", headers=headers)).json()
    assert len(runs) >= 4 and runs[0]["trigger"] == "sync-offline"

    # validation humaine : le patient ne peut pas valider, un médecin oui → plans actifs
    pid = (await client.get("/api/care-program", headers=headers)).json()["id"]
    assert (await client.post(f"/api/care-program/{pid}/validate", json={}, headers=headers)).status_code == 403
    doc = await client.post("/api/v1/auth/login", json={"email": "dr.ahmed@hackcure.org", "password": "Test123!@#"})
    dh = {"Authorization": f"Bearer {doc.json()['access_token']}"}
    assert (await client.post(f"/api/care-program/{pid}/validate", json={}, headers=dh)).json()["status"] == "applied"
    final = (await client.get("/api/care-program", headers=headers)).json()
    assert final["validation"]["label"] == agent.DOCTOR_LABEL and final["validation"]["validated_by"] == "dr.ahmed@hackcure.org"
    async with AsyncSessionLocal() as db:
        plans = (await db.execute(select(NutritionPlan).where(NutritionPlan.patient_id == patient.id, NutritionPlan.status == NutritionPlanStatus.ACTIVE))).scalars().all()
        assert len(plans) == 1 and plans[0].foods_to_avoid


async def test_demo_auto_apply_is_labelled(client, hospital, monkeypatch):
    headers, patient = await zohra(client)
    monkeypatch.setattr(settings, "DEMO_AUTO_APPLY", True)
    res = await client.post("/api/hospital-link", json={"pseudonym": "PAT-0004", "date_of_birth": demo_birth_date().isoformat(), "consent": True}, headers=headers)
    assert res.status_code == 200 and res.json()["last_agent_run"]["steps"][3]["detail"] == "Validé automatiquement — mode démonstration"
    prog = (await client.get("/api/care-program", headers=headers)).json()
    assert prog["validation"]["status"] == "applied" and prog["validation"]["auto_applied"] is True and prog["validation"]["label"] == "Validé automatiquement — mode démonstration"


async def test_subscription_is_required_and_shares_revenue(client, hospital):
    async with AsyncSessionLocal() as db:
        user = User(id=uuid.uuid4(), email=f"sans-abonnement-{uuid.uuid4().hex[:8]}@example.com", password_hash=get_password_hash("x"), role=UserRole.PATIENT, is_active=True, language="fr")
        patient = Patient(id=uuid.uuid4(), user_id=user.id, first_name="Test", last_name="Abonnement", date_of_birth=demo_birth_date(), gender=Gender.FEMALE)
        db.add_all([user, patient])
        await db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}
    sub = (await client.get("/api/subscription", headers=headers)).json()
    assert sub["status"] == "none" and sub["active"] is False and sub["hospital_share_pct"] + sub["team_share_pct"] == 100
    body = {"pseudonym": "PAT-0004", "date_of_birth": demo_birth_date().isoformat(), "consent": True}
    assert (await client.post("/api/hospital-link", json=body, headers=headers)).status_code == 402
    active = (await client.post("/api/subscription/activate", json={"plan": "monthly"}, headers=headers)).json()
    assert active["active"] and active["status"] == "active" and active["plan"] == "monthly" and active["demo"] is True and active["hospital_share_pct"] == settings.SUBSCRIPTION_HOSPITAL_SHARE_PCT
    # le séjour PAT-0004 est déjà lié au compte de démonstration : un second compte ne peut pas le prendre
    zh, _ = await zohra(client)
    assert (await client.post("/api/hospital-link", json=body, headers=zh)).status_code == 200
    assert (await client.post("/api/hospital-link", json=body, headers=headers)).status_code == 409
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Subscription).where(Subscription.patient_id == patient.id))
        await db.commit()


async def test_three_missed_critical_doses_notify_patient_and_care_team(client, hospital):
    headers, patient = await zohra(client)
    await client.post("/api/hospital-link", json={"pseudonym": "PAT-0004", "date_of_birth": demo_birth_date().isoformat(), "consent": True}, headers=headers)
    async with AsyncSessionLocal() as db:
        item = (await db.execute(select(PrescriptionItem).join(Prescription).where(Prescription.patient_id == patient.id, Prescription.is_current.is_(True), PrescriptionItem.medication_name.like("Énoxaparine%")))).scalar_one()
        for n in (1, 2, 3):
            db.add(MedicationDose(patient_id=patient.id, prescription_item_id=item.id, scheduled_date=date.today() - timedelta(days=n), scheduled_time=time(20, 0), status=DoseStatus.MISSED))
        await db.commit()
    run = (await client.post("/api/agent/run", headers=headers)).json()
    assert "ALERTE" in run["steps"][-1]["detail"] and "Énoxaparine" in run["care_team_note"] and "PAT-" not in run["care_team_note"].replace("Patient  :", "")
    async with AsyncSessionLocal() as db:
        notes = (await db.execute(select(Notification).where(Notification.user_id == patient.user_id, Notification.title == "Prises manquées"))).scalars().all()
        assert len(notes) == 1 and "sans doubler la dose" in notes[0].body
    await client.post("/api/agent/run", headers=headers)                                    # pas de seconde notification le même jour
    async with AsyncSessionLocal() as db:
        assert len((await db.execute(select(Notification).where(Notification.user_id == patient.user_id, Notification.title == "Prises manquées"))).scalars().all()) == 1
        await db.execute(delete(MedicationDose).where(MedicationDose.patient_id == patient.id, MedicationDose.status == DoseStatus.MISSED))
        await db.commit()


# ── Sakina ───────────────────────────────────────────────────────────────────
async def test_sakina_is_grounded_refuses_dose_changes_and_keeps_the_crisis_protocol(client, hospital):
    headers, patient = await zohra(client)
    await client.post("/api/hospital-link", json={"pseudonym": "PAT-0004", "date_of_birth": demo_birth_date().isoformat(), "consent": True}, headers=headers)

    async def chat(text, history=()):
        res = await client.post("/api/chat", json={"history": [*history, {"role": "user", "content": text}]}, headers=headers)
        assert res.status_code == 200, res.text
        return res.json()

    # sans crédit : réponse de soutien préparée, fondée sur l'ordonnance réelle
    a = await chat("Bonjour, quels médicaments je dois prendre ?")
    assert a["fallback"] is True and a["mode"] == "offline_support" and a["crisis"] is False
    assert "Énoxaparine" in a["reply"] or "Paracétamol" in a["reply"]
    assert a["context_used"]["grounded"] is True and a["context_used"]["label"] == "Basé sur votre ordonnance du 10/10/2026" and "programme de vie" in a["context_used"]["sources"]
    assert "Chaabane" not in a["reply"]
    # refus de modifier une dose : déterministe, renvoi vers le médecin
    for text in ("Je peux doubler ma dose de paracétamol ce soir ?", "J'ai envie d'arrêter mon traitement, ça me fatigue", "Can I skip my medication today?",
                 "Je peux arrêter le Lovenox ?", "et si je saute l'énoxaparine ce soir"):
        r = await chat(text)
        assert r["mode"] == "safety" and r["crisis"] is False and ("médecin" in r["reply"] or "doctor" in r["reply"]), text
        assert "ne peux pas modifier" in r["reply"] or "can't change" in r["reply"]
    # protocole de crise inchangé : prioritaire, numéros d'urgence, pas de contexte
    c = await chat("je veux me suicider")
    assert c["crisis"] is True and c["emergency_numbers"] and c["mode"] == "llm" and c["context_used"] is None and "urgence" in c["reply"].lower()
    still = await chat("et mon ordonnance ?", history=[{"role": "user", "content": "je veux me suicider"}, {"role": "assistant", "content": c["reply"]}])
    assert still["crisis"] is True                                                           # la crise reste prioritaire tant que la sécurité n'est pas confirmée
    # avec un LLM (simulé) : le contexte hospitalier est bien injecté dans le prompt
    seen = {}

    async def fake_llm(model, system, messages, max_tokens):
        seen["system"] = system
        return "Je vous écoute."

    from app.services import sakina as sakina_service

    import pytest as _pytest
    mp = _pytest.MonkeyPatch()
    mp.setattr(sakina_service, "_anthropic", fake_llm)
    try:
        ok = await chat("Je me sens fatiguée depuis mon retour")
    finally:
        mp.undo()
    assert ok["mode"] == "llm" and ok["fallback"] is False and ok["reply"] == "Je vous écoute."
    assert "Patient context" in seen["system"] and "Énoxaparine" in seen["system"] and "prothèse" in seen["system"] and "Chaabane" not in seen["system"] and "Zohra" not in seen["system"]
