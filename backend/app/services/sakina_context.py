"""
Contexte de Sakina fondé sur le dossier hospitalier synchronisé, et réponses de soutien SANS LLM.

- `build_context` : rassemble, pour le patient connecté, ce que l'hôpital a transmis (problèmes, allergies, rapport,
  ordonnance, état psychologique s'il existe), le programme de vie en cours, l'observance et la prochaine prise.
  Aucun nom : uniquement des données cliniques (le texte est en plus passé par le filtre d'identifiants existant).
- `is_treatment_change_request` : détection déterministe d'une demande de modification de traitement ; la réponse est
  toujours un refus bienveillant avec renvoi vers le médecin (jamais le LLM).
- `offline_support_reply` : mode sans crédit — réponses préparées, adaptées au contexte (prochaine prise, progrès
  d'observance, conseil du jour). Plus pauvres qu'un LLM, mais utilisables et sûres.

Le protocole de crise (`services/sakina.py`) n'est pas touché : il s'applique AVANT tout ce qui est ici.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import care_plan_agent
from app.integrations import hospital_copilot as hc
from app.models.dose import DoseStatus, MedicationDose
from app.models.hospital_link import HospitalLink
from app.models.medication import PrescriptionItem
from app.models.patient import Patient
from app.models.prescription import Prescription
from app.services.companion import _redact_direct_identifiers
from app.services.dose_status import patient_now

_CHANGE_VERBS = r"(arr[êe]t\w*|stopp?\w*|augment\w*|diminu\w*|r[ée]dui\w*|doubl\w*|saut\w*|chang\w*|modifi\w*|rempla[cç]\w*|baiss\w*|supprim\w*|ne plus prendre|stop|increase|reduce|double|skip|change|lower|quit)"
_CHANGE_OBJECTS = r"(dose|dosage|posologie|m[ée]dicament\w*|traitement|comprim[ée]\w*|g[ée]lule\w*|cachet\w*|insuline|pilule\w*|medication|medicine|pill\w*|tablet\w*|treatment)"
_CHANGE_RE = re.compile(rf"{_CHANGE_VERBS}.{{0,60}}{_CHANGE_OBJECTS}|{_CHANGE_OBJECTS}.{{0,60}}{_CHANGE_VERBS}", re.I)
_CHANGE_AR = ("نبدل الجرعة", "نوقف الدواء", "نزيد الجرعة", "ننقص الجرعة", "أوقف الدواء", "أغير الجرعة", "تغيير الجرعة", "نحبس الدواء", "ما نشربش الدواء")


def medication_words(names: list[str]) -> list[str]:
    """Mots qui désignent les médicaments du patient : « Énoxaparine 4000 UI (Lovenox) » → énoxaparine, lovenox."""
    words: list[str] = []
    for name in names or []:
        for w in re.findall(r"[^\W\d_]{4,}", str(name).casefold()):
            if w not in ("comprimé", "gélule", "sirop", "injectable", "avec", "pour") and w not in words:
                words.append(w)
    return words


def is_treatment_change_request(message: str, medication_names: Optional[list[str]] = None) -> bool:
    """Vrai si le message demande d'arrêter, sauter, doubler, augmenter, diminuer ou changer un traitement —
    que le patient dise « mon médicament », « ma dose » ou le nom d'un médicament de son ordonnance."""
    text = message.casefold()
    if _CHANGE_RE.search(text) or any(term in message for term in _CHANGE_AR):
        return True
    words = medication_words(medication_names or [])
    return bool(words) and bool(re.search(_CHANGE_VERBS, text, re.I)) and any(w in text for w in words)


def _fr_date(value: Optional[str]) -> str:
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return ""


async def build_context(db: AsyncSession, patient: Patient) -> dict[str, Any]:
    """Renvoie {text, used: {grounded, label, sources}, facts} — `facts` sert aux réponses sans LLM."""
    facts: dict[str, Any] = {"medications": [], "next_dose": None, "adherence": None, "tip": None, "conditions": [], "allergies": [], "psych": None, "doctor": "", "rx_date": None}
    parts: list[str] = []
    sources: list[str] = []
    link = (await db.execute(select(HospitalLink).where(HospitalLink.patient_id == patient.id, HospitalLink.revoked_at.is_(None)))).scalar_one_or_none()
    params = None
    if link and link.cached_bundle:
        parsed = hc.parse_bundle(link.cached_bundle)
        params = care_plan_agent.extract_parameters(parsed, patient.allergies if isinstance(patient.allergies, list) else None)
        facts.update(conditions=params["conditions"], allergies=params["allergies"], psych=params.get("psych"), doctor=params.get("doctor") or "", rx_date=params.get("document_date"))
        if params["conditions"]:
            parts.append("Problèmes de santé connus (dossier hospitalier) : " + "; ".join(params["conditions"][:8]))
        if params["admission_reasons"]:
            parts.append("Motif du séjour : " + "; ".join(params["admission_reasons"][:3]))
        if params["allergies"]:
            parts.append("Allergies : " + ", ".join(params["allergies"]))
        for d in hc.stay_documents(parsed)[:2]:
            parts.append(f"{'Rapport de sortie' if d['kind'] == 'discharge' else 'Rapport médical'} du {_fr_date(d.get('date'))} : {d.get('text', '')[:1500]}")
            sources.append(("rapport de sortie" if d["kind"] == "discharge" else "rapport médical") + (f" du {_fr_date(d.get('date'))}" if d.get("date") else ""))
        if params.get("psych"):
            parts.append(f"État psychologique évalué à l'hôpital : {params['psych'].get('label')} = {params['psych'].get('value')}. {params['psych'].get('note') or ''}")
            sources.append("évaluation psychologique de l'hôpital")
        if params["doctor_instructions"]:
            parts.append("Consignes du médecin : " + " | ".join(params["doctor_instructions"][:6]))
    items = (await db.execute(select(PrescriptionItem).join(Prescription, Prescription.id == PrescriptionItem.prescription_id)
                              .where(Prescription.patient_id == patient.id, Prescription.is_current.is_(True)).limit(20))).scalars().all()
    for i in items:
        times = ", ".join(i.scheduled_times or [])
        facts["medications"].append({"name": i.medication_name, "dose": i.dosage, "times": i.scheduled_times or []})
        parts.append(f"Ordonnance : {i.medication_name} — {i.dosage}" + (f" — à {times}" if times else "") + (f" — {i.instructions}" if i.instructions else ""))
    if items:
        when = _fr_date((params or {}).get("document_date"))
        sources.insert(0, "ordonnance" + (f" du {when}" if when else ""))
    now = patient_now(patient).replace(tzinfo=None)
    rows = (await db.execute(
        select(PrescriptionItem.medication_name, PrescriptionItem.dosage, MedicationDose.scheduled_date, MedicationDose.scheduled_time)
        .join(PrescriptionItem, PrescriptionItem.id == MedicationDose.prescription_item_id)
        .where(MedicationDose.patient_id == patient.id, MedicationDose.status.in_([DoseStatus.SCHEDULED, DoseStatus.DUE, DoseStatus.REMINDING]), MedicationDose.scheduled_date >= now.date())
        .order_by(MedicationDose.scheduled_date, MedicationDose.scheduled_time).limit(40))).all()
    nxt = next((r for r in rows if datetime.combine(r[2], r[3]) >= now), None)
    if nxt:
        facts["next_dose"] = {"name": nxt[0], "dose": nxt[1], "time": nxt[3].strftime("%H:%M"), "today": nxt[2] == now.date()}
        parts.append(f"Prochaine prise prévue : {nxt[0]} ({nxt[1]}) à {nxt[3].strftime('%H:%M')}" + ("" if nxt[2] == now.date() else " demain"))
    adh = await care_plan_agent.adherence(db, patient.id)
    facts["adherence"] = adh
    if adh.get("rate_7d") is not None:
        parts.append(f"Observance sur 7 jours : {round(adh['rate_7d'] * 100)} % ({adh['taken_7d']} prises sur {adh['due_7d']}).")
    program = await care_plan_agent.current_program(db, patient.id)
    if program and program.payload:
        nut, act = program.payload.get("nutrition") or {}, program.payload.get("activity") or {}
        parts.append(f"Programme de vie en cours ({'validé' if program.status == 'applied' else 'brouillon non validé'}) : alimentation « {nut.get('plan_type')} » ; activité « {act.get('activity_name')} », "
                     f"{act.get('duration_minutes')} min, {act.get('frequency_per_week')} fois par semaine.")
        tips = [f"Alimentation : privilégiez {', '.join((nut.get('recommended_foods') or [])[:2])}." if nut.get("recommended_foods") else "",
                f"Activité : {act.get('activity_name')}, {act.get('duration_minutes')} minutes aujourd'hui si vous vous sentez bien." if act.get("activity_name") else ""]
        tips += [f"{h.get('title')} : {h.get('detail')}" for h in (program.payload.get("habits") or [])[:6]]
        tips = [t for t in tips if t]
        if tips:
            facts["tip"] = tips[now.timetuple().tm_yday % len(tips)]
        sources.append("programme de vie")
    text = _redact_direct_identifiers("\n".join(parts)[:7000], patient)
    grounded = bool(items or (link and link.cached_bundle))
    label = ("Basé sur votre " + sources[0]) if sources else "Aucune donnée médicale liée : réponse générale"
    return {"text": text, "used": {"grounded": grounded, "label": label, "sources": sources}, "facts": facts}


# ── réponses sans LLM ────────────────────────────────────────────────────────
def treatment_change_reply(language: str, facts: dict[str, Any]) -> str:
    """Refus bienveillant, toujours le même principe : seul le médecin modifie un traitement."""
    doctor = facts.get("doctor") or ""
    if language == "ar":
        return "أفهم أنك تتساءل عن علاجك، وهذا طبيعي. لا أستطيع تغيير دواء أو جرعة أو توقيت: هذا قرار طبيبك فقط. واصل علاجك كما هو مكتوب في الوصفة، واتصل بطبيبك أو بالصيدلي لتشرح له ما يزعجك. هل تريد أن نحضّر معاً ما ستقوله له؟"
    if language == "en":
        return "I understand you're wondering about your treatment — that's a fair question. I can't change a medicine, a dose or a schedule: only your doctor can. Please keep taking your treatment as prescribed and contact your doctor or pharmacist to explain what is bothering you. Would you like us to prepare what you'll tell them?"
    who = f" ({doctor})" if doctor else ""
    return ("Je comprends que vous vous posiez des questions sur votre traitement, c'est légitime. Je ne peux pas modifier un médicament, une dose ou un horaire : "
            f"seul votre médecin{who} peut le faire. Continuez votre traitement tel qu'il est prescrit, sans doubler ni sauter de prise, et contactez votre médecin ou votre pharmacien "
            "pour lui expliquer ce qui vous gêne. Voulez-vous que nous préparions ensemble ce que vous allez lui dire ?")


_TOPICS = {
    "medication": ("médicament", "medicament", "prise", "comprimé", "traitement", "ordonnance", "rappel", "dose", "medicine", "medication", "pill", "دواء", "جرعة"),
    "food": ("manger", "repas", "aliment", "régime", "regime", "faim", "sel", "sucre", "eat", "food", "diet", "meal", "ماكلة", "أكل"),
    "activity": ("marche", "sport", "bouger", "exercice", "activité", "activite", "kiné", "walk", "exercise", "رياضة", "مشي"),
    "sleep": ("dormir", "sommeil", "insomnie", "fatigue", "fatigué", "sleep", "tired", "نوم", "تعب"),
    "low": ("triste", "seul", "peur", "angoisse", "anxieu", "stress", "inquiet", "inquiète", "déprim", "moral", "pleur", "sad", "alone", "afraid", "anxious", "worried", "حزين", "خايف", "قلق"),
}


def _topic(message: str) -> str:
    text = message.casefold()
    for name in ("low", "medication", "food", "activity", "sleep"):
        if any(w in text for w in _TOPICS[name]):
            return name
    return "general"


def offline_support_reply(message: str, language: str, context: dict[str, Any]) -> str:
    """Réponse de soutien préparée (aucun LLM) : écoute, reformulation, renforcement des progrès, un petit objectif."""
    f = context.get("facts") or {}
    nxt, adh, tip = f.get("next_dose"), f.get("adherence") or {}, f.get("tip")
    topic = _topic(message)
    rate = adh.get("rate_7d")
    if language == "ar":
        parts = ["شكراً لأنك شاركتني ما تشعر به. أنا هنا لأسمعك." if topic == "low" else "شكراً على رسالتك، أنا معك."]
        if nxt:
            parts.append(f"موعد دوائك القادم: {nxt['name']} على الساعة {nxt['time']}.")
        if rate is not None and rate >= 0.8:
            parts.append("أنت ملتزم بعلاجك هذا الأسبوع، وهذا تقدم حقيقي.")
        parts.append("ما هو الشيء الصغير الذي يمكنك فعله اليوم ليريحك قليلاً؟")
        return " ".join(parts)
    if language == "en":
        parts = ["Thank you for telling me how you feel. I'm here and I'm listening." if topic == "low" else "Thank you for your message — I'm with you."]
        if topic in ("medication", "general") and nxt:
            parts.append(f"Your next dose is {nxt['name']} ({nxt['dose']}) at {nxt['time']}{'' if nxt.get('today') else ' tomorrow'}.")
        if rate is not None:
            parts.append("You've kept up with your treatment this week — that is real progress." if rate >= 0.8 else "Some doses were missed this week; let's simply aim for the next one.")
        if tip and topic in ("food", "activity", "sleep", "general"):
            parts.append("From your programme: " + tip)
        parts.append("What is one small thing you could do today that would help a little?")
        return " ".join(parts)
    openers = {"low": "Merci de me confier ce que vous ressentez ; ce n'est pas facile et vous avez bien fait d'en parler. Je suis là pour vous écouter.",
               "medication": "Merci pour votre question sur votre traitement.", "food": "Bonne question sur votre alimentation.", "activity": "C'est une bonne idée de penser à bouger.",
               "sleep": "Le sommeil compte beaucoup pendant la convalescence.", "general": "Merci pour votre message, je suis là."}
    parts = [openers[topic]]
    if topic in ("medication", "general") and nxt:
        parts.append(f"Votre prochaine prise est {nxt['name']} ({nxt['dose']}) à {nxt['time']}{'' if nxt.get('today') else ' demain'}.")
    if topic == "medication" and f.get("medications"):
        parts.append("Votre ordonnance comprend : " + " ; ".join(f"{m['name']} {m['dose']}" for m in f["medications"][:4]) + ".")
    if rate is not None:
        parts.append(f"Vous avez pris {round(rate * 100)} % de vos médicaments cette semaine : " + ("c'est un vrai progrès, bravo." if rate >= 0.8 else "avançons pas à pas, en commençant par la prochaine prise."))
    if tip and topic in ("food", "activity", "sleep", "general"):
        parts.append("Dans votre programme : " + tip)
    parts.append("Quel petit pas, même tout simple, pourriez-vous faire aujourd'hui ?" if topic != "low" else "Qu'est-ce qui vous pèse le plus en ce moment ?")
    return " ".join(parts)
