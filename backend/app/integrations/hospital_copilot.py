"""
Client de la plateforme hospitalière Hospital Copilot (API HL7 FHIR R4 en lecture).

- `HOSPITAL_COPILOT_URL` (défaut http://localhost:8000) et `HOSPITAL_COPILOT_SERVICE_TOKEN` (le `PLATFORM_SERVICE_TOKEN`
  de l'hôpital, envoyé en `Authorization: Bearer`).
- Délai d'attente, nouvelles tentatives avec temporisation, et **cache local** : le dernier Bundle reçu est gardé dans
  `HospitalLink.cached_bundle`, la dernière synchronisation reste donc disponible hors ligne.
- **Aucun nom n'est conservé** : le jeton de service de l'hôpital a le droit de voir l'identité, donc la ressource
  Patient peut contenir `name` ; `sanitize_bundle` le retire dès la réception (ainsi que l'adresse et le téléphone).
  Seuls le pseudonyme (`PAT-xxxx`) et les données cliniques sont gardés.

Fonctions pures (`parse_bundle`, `sanitize_bundle`, `bundle_digest`) testées sans réseau.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
from datetime import date, datetime
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PSEUDONYM_RE = re.compile(r"^PAT-\d{4,6}$")
IDENTITY_KEYS = ("name", "telecom", "address", "photo", "contact")
LOINC = {"8867-4": "hr", "59408-5": "spo2", "2708-6": "spo2", "8480-6": "sys", "8462-4": "dia", "8310-5": "temp", "9279-1": "rr", "41653-7": "glucose", "2339-0": "glucose", "85354-9": "bp"}
DEFAULT_TIMES = {1: ["08:00"], 2: ["08:00", "20:00"], 3: ["08:00", "14:00", "20:00"], 4: ["08:00", "12:00", "16:00", "20:00"]}


class HospitalUnavailable(Exception):
    """La plateforme hospitalière ne répond pas (réseau, arrêt, délai dépassé)."""


class HospitalRejected(Exception):
    """La plateforme a répondu par un refus (jeton invalide, patient inconnu…)."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status, self.detail = status, detail


def normalize_pseudonym(value: str) -> str:
    v = (value or "").strip().upper().replace(" ", "")
    if v.startswith("PATIENT/"):
        v = v.split("/", 1)[1]
    return v


def configured() -> bool:
    return bool(settings.HOSPITAL_COPILOT_URL and settings.HOSPITAL_COPILOT_SERVICE_TOKEN)


class HospitalCopilotClient:
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None, timeout: Optional[float] = None, retries: Optional[int] = None, transport: Any = None):
        self.base_url = (base_url or settings.HOSPITAL_COPILOT_URL).rstrip("/")
        self.token = token if token is not None else settings.HOSPITAL_COPILOT_SERVICE_TOKEN
        self.timeout = timeout or settings.HOSPITAL_COPILOT_TIMEOUT_SECONDS
        self.retries = retries if retries is not None else settings.HOSPITAL_COPILOT_RETRIES
        self.transport = transport  # tests : httpx.MockTransport / ASGITransport

    async def _get(self, path: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/fhir+json"}
        last: Exception | None = None
        for attempt in range(max(1, self.retries)):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport, verify=settings.HOSPITAL_COPILOT_VERIFY_TLS) as client:
                    r = await client.get(self.base_url + path, headers=headers)
                if r.status_code >= 500:
                    last = HospitalUnavailable(f"HTTP {r.status_code}")
                elif r.status_code >= 400:
                    detail = ""
                    try:
                        body = r.json()
                        detail = (body.get("issue") or [{}])[0].get("diagnostics") or body.get("detail") or ""
                    except ValueError:
                        detail = r.text[:200]
                    raise HospitalRejected(r.status_code, str(detail))
                else:
                    return r.json()
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last = HospitalUnavailable(type(exc).__name__)
            if attempt + 1 < self.retries:
                await asyncio.sleep(0.3 * (2 ** attempt))
        raise last or HospitalUnavailable("no response")

    async def patient(self, pseudonym: str) -> dict[str, Any]:
        return await self._get(f"/fhir/Patient/{pseudonym}")

    async def everything(self, pseudonym: str) -> dict[str, Any]:
        return sanitize_bundle(await self._get(f"/fhir/Patient/{pseudonym}/$everything"))

    async def verify_identity(self, pseudonym: str, birth_date: date) -> bool:
        """Vrai si le séjour existe et que la date de naissance correspond. Le nom n'est ni lu ni conservé."""
        resource = await self.patient(pseudonym)
        found = str(resource.get("birthDate") or "")
        if len(found) == 4:  # date réduite à l'année côté hôpital (rôle sans identité) : on compare l'année
            return found == f"{birth_date.year:04d}"
        return found[:10] == birth_date.isoformat()


# ── fonctions pures ──────────────────────────────────────────────────────────
def sanitize_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Retire tout champ d'identité des ressources Patient : seul le pseudonyme et les données cliniques restent."""
    out = json.loads(json.dumps(bundle))
    for entry in out.get("entry", []) or []:
        res = entry.get("resource") or {}
        if res.get("resourceType") == "Patient":
            for key in IDENTITY_KEYS:
                res.pop(key, None)
    return out


def bundle_digest(bundle: dict[str, Any]) -> str:
    """Empreinte du contenu clinique utile au plan (ordonnances, documents, problèmes, allergies) : change ⇒ l'agent repasse."""
    keep = []
    for entry in bundle.get("entry", []) or []:
        res = entry.get("resource") or {}
        if res.get("resourceType") in ("MedicationRequest", "DocumentReference", "Condition", "AllergyIntolerance"):
            slim = {k: v for k, v in res.items() if k not in ("meta",)}
            keep.append(json.dumps(slim, sort_keys=True, ensure_ascii=False))
    return hashlib.sha256("\n".join(sorted(keep)).encode("utf-8")).hexdigest()


def _text(concept: Any) -> str:
    if not isinstance(concept, dict):
        return ""
    if concept.get("text"):
        return str(concept["text"])
    for c in concept.get("coding") or []:
        if c.get("display"):
            return str(c["display"])
    return ""


def _codes(concept: Any) -> list[str]:
    return [str(c.get("code")) for c in ((concept or {}).get("coding") or []) if c.get("code")]


def _day(value: Any) -> Optional[str]:
    return str(value)[:10] if value else None


def parse_medication_request(res: dict[str, Any]) -> dict[str, Any]:
    """MedicationRequest → médicament structuré. Rien n'est inventé : ce qui manque dans l'ordonnance reste vide."""
    dosage = (res.get("dosageInstruction") or [{}])[0] or {}
    repeat = ((dosage.get("timing") or {}).get("repeat")) or {}
    times = [str(t)[:5] for t in (repeat.get("timeOfDay") or []) if re.match(r"^\d{2}:\d{2}", str(t))]
    freq = repeat.get("frequency")
    period, unit = repeat.get("period", 1), repeat.get("periodUnit", "d")
    per_day: Optional[int] = None
    if isinstance(freq, (int, float)) and freq and unit == "d" and period in (1, 1.0):
        per_day = int(freq)
    elif isinstance(freq, (int, float)) and freq and unit == "h" and period:
        per_day = max(1, int(round(24 / float(period) * float(freq))))
    if per_day is None and times:
        per_day = len(times)
    dose_q = (((dosage.get("doseAndRate") or [{}])[0] or {}).get("doseQuantity")) or {}
    dose = f"{dose_q.get('value'):g} {dose_q.get('unit') or dose_q.get('code') or ''}".strip() if isinstance(dose_q.get("value"), (int, float)) else ""
    text = str(dosage.get("text") or "")
    if not dose and text:
        dose = text.split(" · ")[0].strip()
    bounds = repeat.get("boundsDuration") or {}
    duration = int(bounds["value"]) if isinstance(bounds.get("value"), (int, float)) and bounds.get("value") else None
    category = next((c for cat in (res.get("category") or []) for c in _codes(cat)), "") or ""
    times_source = "ordonnance"
    if not times and per_day in DEFAULT_TIMES:  # la fréquence vient de l'ordonnance ; les heures sont la convention de l'application
        times, times_source = list(DEFAULT_TIMES[per_day]), "convention"
    return {
        "id": res.get("id"), "name": _text(res.get("medicationCodeableConcept")) or "Médicament", "dose": dose, "dosage_text": text,
        "route": _text(dosage.get("route")), "per_day": per_day, "times": times, "times_source": times_source if times else "absent",
        "duration_days": duration, "as_needed": bool(dosage.get("asNeededBoolean")), "category": category, "status": res.get("status") or "",
        "authored_on": _day(res.get("authoredOn")), "requester": ((res.get("requester") or {}).get("display")) or "",
        "indication": "; ".join(_text(r) for r in (res.get("reasonCode") or []) if _text(r)),
        "notes": [n.get("text") for n in (res.get("note") or []) if n.get("text")],
    }


def parse_document(res: dict[str, Any]) -> dict[str, Any]:
    att = ((res.get("content") or [{}])[0] or {}).get("attachment") or {}
    text = ""
    if att.get("data"):
        try:
            text = base64.b64decode(att["data"]).decode("utf-8", errors="replace")
        except Exception:
            text = ""
    codes = _codes(res.get("type"))
    kind = "discharge" if "18842-5" in codes else "report"
    return {"id": res.get("id"), "kind": kind, "title": att.get("title") or res.get("description") or _text(res.get("type")) or "Document",
            "date": _day(res.get("date")), "author": ((res.get("author") or [{}])[0] or {}).get("display") or "", "text": text}


def parse_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Bundle `$everything` → paramètres cliniques structurés pour le CarePlanAgent et le chatbot."""
    out: dict[str, Any] = {"patient": {}, "conditions": [], "allergies": [], "encounters": [], "vitals": {}, "labs": [], "medications": [], "documents": [], "psych": None}
    for entry in bundle.get("entry", []) or []:
        res = entry.get("resource") or {}
        rtype = res.get("resourceType")
        if rtype == "Patient":
            pseudo = res.get("id") or next((i.get("value") for i in res.get("identifier") or [] if i.get("value")), None)
            birth = str(res.get("birthDate") or "")
            age = None
            if len(birth) >= 4 and birth[:4].isdigit():
                today = date.today()
                age = today.year - int(birth[:4])
                if len(birth) >= 10:
                    try:
                        b = date.fromisoformat(birth[:10])
                        age = today.year - b.year - ((today.month, today.day) < (b.month, b.day))
                    except ValueError:
                        pass
            out["patient"] = {"pseudonym": pseudo, "gender": res.get("gender"), "age": age, "birth_year": birth[:4] or None}
        elif rtype == "Condition":
            label = _text(res.get("code"))
            if label:
                cats = [c for cat in (res.get("category") or []) for c in _codes(cat)]
                out["conditions"].append({"text": label, "category": cats[0] if cats else "", "onset": _day(res.get("onsetDateTime"))})
        elif rtype == "AllergyIntolerance":
            label = _text(res.get("code"))
            if label:
                out["allergies"].append(label)
        elif rtype == "Encounter":
            out["encounters"].append({"status": res.get("status"), "start": _day((res.get("period") or {}).get("start")), "end": _day((res.get("period") or {}).get("end")),
                                      "reason": "; ".join(_text(r) for r in (res.get("reasonCode") or []) if _text(r))})
        elif rtype == "Observation":
            codes = _codes(res.get("code"))
            key = next((LOINC[c] for c in codes if c in LOINC), None)
            cats = [c for cat in (res.get("category") or []) for c in _codes(cat)]
            if key == "bp":
                for comp in res.get("component") or []:
                    ck = next((LOINC[c] for c in _codes(comp.get("code")) if c in LOINC), None)
                    v = (comp.get("valueQuantity") or {}).get("value")
                    if ck and v is not None:
                        out["vitals"][ck] = v
            elif key and (res.get("valueQuantity") or {}).get("value") is not None:
                out["vitals"][key] = res["valueQuantity"]["value"]
            elif "laboratory" in cats and (res.get("valueQuantity") or {}).get("value") is not None:
                out["labs"].append({"label": _text(res.get("code")), "value": res["valueQuantity"]["value"], "unit": res["valueQuantity"].get("unit"), "date": _day(res.get("effectiveDateTime"))})
            text = _text(res.get("code")).lower()
            if "bien-être" in text or "wellbeing" in text or "psych" in text:  # état psychologique exporté par l'hôpital, s'il existe
                out["psych"] = {"label": _text(res.get("code")), "value": (res.get("valueQuantity") or {}).get("value"), "note": (res.get("valueString") or "")[:300]}
        elif rtype == "MedicationRequest":
            out["medications"].append(parse_medication_request(res))
        elif rtype == "DocumentReference":
            out["documents"].append(parse_document(res))
    out["documents"].sort(key=lambda d: d.get("date") or "", reverse=True)
    starts = [e["start"] for e in out["encounters"] if e.get("start")]
    since = max(starts) if starts else None  # début du dernier séjour connu
    for d in out["documents"]:
        d["current_stay"] = bool(since and d.get("date") and d["date"] >= since)
    return out


def stay_documents(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Documents du séjour en cours (rapport médical, rapport de sortie). Les comptes rendus d'anciens séjours restent
    dans le dossier synchronisé mais ne servent ni aux consignes ni au chatbot."""
    docs = [d for d in parsed.get("documents", []) if d.get("current_stay")]
    return docs or parsed.get("documents", [])[:1]


def discharge_medications(parsed: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """Médicaments à suivre à domicile. Priorité à l'ordonnance de sortie ; à défaut, l'ordonnance de traitement active
    (hors « si besoin »). Renvoie (médicaments, origine)."""
    meds = [m for m in parsed.get("medications", []) if m.get("status") in ("active", "completed", "") and not m.get("as_needed")]
    discharge = [m for m in meds if m.get("category") == "discharge"]
    if discharge:
        return discharge, "ordonnance de sortie"
    active = [m for m in meds if m.get("status") == "active"]
    return active, "ordonnance de traitement"
