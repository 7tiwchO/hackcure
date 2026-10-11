"""
CarePlanAgent — l'agent qui transforme le séjour hospitalier en programme à domicile.
Il s'exécute DANS le backend Python (pas de n8n) à chaque synchronisation avec Hospital Copilot ou nouvelle ordonnance.

Étapes d'une exécution (chacune est journalisée) :
1. extraction  : paramètres cliniques tirés des données hospitalières (diagnostic, maladies chroniques, allergies,
                 traitements, constantes, consignes du médecin dans le rapport) ;
2. médicaments : DÉTERMINISTE, sans LLM. L'ordonnance structurée devient un brouillon `DocumentSource` puis des
                 `PrescriptionItem` + `MedicationDose` par le pipeline existant (`execute_apply_drafts`).
                 L'IA ne touche jamais à un médicament, une dose ou un horaire ;
3. programme   : alimentation, activité, habitudes. LLM encadré par des garde-fous, ou — si le LLM est indisponible —
                 plan produit par les mêmes règles (mode de secours, signalé dans l'interface) ;
4. validation  : le programme reste en BROUILLON avec sa source et son indice de confiance, jusqu'à validation par un
                 médecin (flux `apply` existant). `DEMO_AUTO_APPLY=true` l'applique tout de suite, avec la mention
                 « Validé automatiquement — mode démonstration » ;
5. suivi       : observance (prises manquées, tendance), message d'encouragement, notification au patient et
                 signalement pour l'équipe soignante après 3 prises manquées de suite d'un médicament critique.

Les fonctions `extract_parameters`, `rule_based_plan`, `apply_guardrails`, `medication_payload` sont pures et testées.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime, time, timedelta
from time import monotonic
from typing import Any, Optional

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.integrations.hospital_copilot import discharge_medications, stay_documents
from app.models.audit_log import AuditLog
from app.models.document_source import DocumentSource, DocumentStatus, DocumentType
from app.models.dose import DoseStatus, MedicationDose
from app.models.hospital_link import AgentRun, CareProgram
from app.models.medication import PrescriptionItem
from app.models.notification import Notification, NotificationCategory, NotificationPriority
from app.models.patient import Patient
from app.schemas.automation import ApplyPayload

logger = logging.getLogger(__name__)

AUTO_LABEL = "Validé automatiquement — mode démonstration"
DRAFT_LABEL = "Brouillon — en attente de validation médicale"
DOCTOR_LABEL = "Validé par le médecin"
DISCLAIMER = "Conseils d'hygiène de vie, dans les limites fixées par votre médecin. Ils ne remplacent pas un avis médical."

# ── 1. extraction des paramètres ─────────────────────────────────────────────
FLAGS = {
    "heart_failure": ("insuffisance cardiaque", "décompensation cardiaque", "fevg"),
    "hypertension": ("hypertension", "hta"),
    "diabetes": ("diabète", "diabete", "diabétique"),
    "copd": ("bpco", "bronchopneumopathie", "insuffisance respiratoire"),
    "renal": ("insuffisance rénale", "néphropathie", "dialyse"),
    "dysphagia": ("déglutition", "dysphagie", "fausse route", "fausses routes"),
    "ortho": ("prothèse", "fracture", "col du fémur", "col fémoral", "hanche", "arthroplastie", "ostéosynthèse"),
    "anemia": ("anémie",),
    "osteoporosis": ("ostéoporose",),
    "fall_risk": ("chute", "risque de chute", "troubles de la marche"),
    "afib": ("fibrillation",),
    "malnutrition": ("dénutrition",),
    "epilepsy": ("épilepsie", "epilepsie"),
    "infection": ("pneumopathie", "sepsis", "infection"),
}
ANTICOAGULANTS = ("apixaban", "eliquis", "rivaroxaban", "xarelto", "dabigatran", "warfarine", "coumadine", "avk", "acénocoumarol", "sintrom", "héparine", "heparine", "énoxaparine", "enoxaparine", "lovenox")
CRITICAL_MEDS = ANTICOAGULANTS + ("insuline", "insulin", "lévétiracétam", "levetiracetam", "keppra", "bisoprolol", "métoprolol", "amiodarone", "digoxine", "furosémide", "furosemide", "lasilix",
                                  "clopidogrel", "amoxicilline", "antibio", "ceftriaxone", "méthotrexate", "prednis", "lévothyrox")
INSTRUCTION_HINTS = ("régime", "regime", "alimentation", "sel", "sucre", "boire", "hydrat", "repos", "éviter", "eviter", "marche", "kiné", "kine", "rééducation", "reeducation", "appui", "effort",
                     "surveill", "contrôle", "controle", "poids", "tension", "glycémie", "glycemie", "tabac", "alcool", "sommeil", "pansement", "consultation", "rendez-vous")


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def extract_parameters(parsed: dict[str, Any], app_allergies: Optional[list[str]] = None) -> dict[str, Any]:
    """Paramètres cliniques utiles au programme, tirés du Bundle hospitalier déjà analysé (`parse_bundle`)."""
    patient = parsed.get("patient") or {}
    conditions = [c["text"] for c in parsed.get("conditions", []) if c.get("text")]
    reasons = [e["reason"] for e in parsed.get("encounters", []) if e.get("reason")]
    docs = stay_documents(parsed)
    corpus = " ".join(conditions + reasons + [d.get("text", "") for d in docs]).lower()
    meds, origin = discharge_medications(parsed)
    med_text = " ".join((m.get("name") or "") for m in parsed.get("medications", [])).lower()
    flags = {k: _has(corpus, words) for k, words in FLAGS.items()}
    flags["anticoagulant"] = _has(med_text, ANTICOAGULANTS)
    if "insuline" in med_text or "metformine" in med_text:
        flags["diabetes"] = True
    instructions: list[str] = []
    for d in docs:  # consignes du médecin : phrases du rapport qui parlent d'hygiène de vie ou de surveillance
        for sentence in re.split(r"(?<=[.;!?])\s+|\n+", d.get("text", "")):
            s = sentence.strip(" -•\t")
            if 12 <= len(s) <= 260 and _has(s.lower(), INSTRUCTION_HINTS) and s not in instructions:
                instructions.append(s)
    allergies = list(dict.fromkeys([a for a in (parsed.get("allergies") or []) + (app_allergies or []) if a]))
    last_doc = docs[0] if docs else None
    requester = next((m.get("requester") for m in meds if m.get("requester")), "") or (last_doc or {}).get("author", "")
    authored = next((m.get("authored_on") for m in meds if m.get("authored_on")), None) or (last_doc or {}).get("date")
    return {
        "pseudonym": patient.get("pseudonym"), "age": patient.get("age"), "gender": patient.get("gender"),
        "conditions": conditions, "admission_reasons": reasons, "allergies": allergies, "flags": flags,
        "vitals": parsed.get("vitals") or {}, "psych": parsed.get("psych"),
        "medications": [{"name": m["name"], "dose": m["dose"], "times": m["times"], "per_day": m["per_day"], "duration_days": m["duration_days"]} for m in meds],
        "medication_origin": origin, "doctor_instructions": instructions[:6],
        "doctor": requester, "document_date": authored,
        "documents": [{"kind": d["kind"], "title": d["title"], "date": d["date"]} for d in docs],
    }


def source_line(params: dict[str, Any]) -> str:
    doctor, day = params.get("doctor") or "", params.get("document_date")
    when = ""
    if day:
        try:
            when = " du " + date.fromisoformat(str(day)[:10]).strftime("%d/%m/%Y")
        except ValueError:
            when = ""
    who = f" du {doctor}" if doctor.lower().startswith("dr") else (f" de {doctor}" if doctor else "")
    origin = params.get("medication_origin") or "dossier hospitalier"
    return f"issu de l'{origin}{who}{when}" if params.get("medications") else f"issu du dossier hospitalier{who}{when}"


# ── 2. médicaments : strictement l'ordonnance ────────────────────────────────
def medication_payload(patient_id: uuid.UUID, parsed: dict[str, Any], today: Optional[date] = None) -> tuple[dict[str, Any], list[str]]:
    """Ordonnance structurée → charge utile du pipeline existant (`PrescriptionExtractionPayload`). Aucun champ n'est inventé :
    un médicament sans horaire ni fréquence est gardé SANS rappel et signalé."""
    today = today or date.today()
    meds, origin = discharge_medications(parsed)
    warnings: list[str] = []
    items, scores = [], {}
    max_days = 0
    for m in meds:
        if not m["times"]:
            warnings.append(f"{m['name']} : ni horaire ni fréquence dans l'ordonnance — aucun rappel créé, demandez à votre médecin.")
        conf = 1.0 if m["times_source"] == "ordonnance" else (0.8 if m["times_source"] == "convention" else 0.5)
        if m["times_source"] == "convention":
            warnings.append(f"{m['name']} : {m['per_day']} prise(s) par jour selon l'ordonnance ; heures de rappel par défaut ({', '.join(m['times'])}).")
        duration = m["duration_days"] or 30
        max_days = max(max_days, duration)
        items.append({"nom": m["name"], "principe_actif": None, "posologie": m["dose"] or m["dosage_text"] or "selon ordonnance", "forme": None,
                      "frequence": (f"{m['per_day']} fois par jour" if m["per_day"] else (m["dosage_text"] or "selon ordonnance")), "heures_prises": m["times"],
                      "duree_jours": duration, "instructions": " · ".join(x for x in [m["dosage_text"], m["route"], *m["notes"]] if x)[:400] or None, "confidence": conf})
        scores[m["name"]] = conf
    first = meds[0] if meds else {}
    payload = {"patient_id": str(patient_id), "prescription_number": None, "doctor_name": first.get("requester") or None,
               "diagnosis": first.get("indication") or None, "notes": f"Synchronisée depuis Hospital Copilot ({origin})", "date_debut": today.isoformat(),
               "date_fin": (today + timedelta(days=max_days or 30)).isoformat(), "medicaments": items, "confidence_scores": scores}
    return payload, warnings


# ── 3. programme de vie : règles (mode de secours) ───────────────────────────
ALLERGEN_FOODS = {
    "arachide": ("arachide", "cacahuète", "cacahuete"), "peanut": ("arachide", "cacahuète"), "gluten": ("blé", "pain", "pâtes", "semoule", "céréales complètes"),
    "lactose": ("lait", "yaourt", "fromage", "laitage"), "lait": ("lait", "yaourt", "fromage", "laitage"), "poisson": ("poisson", "sardine", "thon"),
    "fruits de mer": ("crevette", "fruits de mer"), "œuf": ("œuf", "oeuf"), "oeuf": ("œuf", "oeuf"), "fruits à coque": ("noix", "amande", "noisette"), "soja": ("soja",),
}


def rule_based_plan(params: dict[str, Any]) -> dict[str, Any]:
    """Plan par règles : mêmes paramètres, mêmes garde-fous que le chemin LLM. Chaque élément porte sa règle et sa confiance."""
    f, age = params.get("flags") or {}, params.get("age") or 0
    src = source_line(params)
    rules: list[str] = []
    recommended = ["légumes à chaque repas", "fruits frais (2 à 3 par jour)", "poisson deux fois par semaine", "huile d'olive", "légumineuses (lentilles, pois chiches)", "céréales complètes"]
    avoid = ["plats industriels et charcuteries", "boissons sucrées", "fritures"]
    plan_type, calories, hydration = "Méditerranéen équilibré", None, 1500
    notes: list[str] = []
    meals = {"petit_dejeuner": "pain complet, fromage frais, un fruit, thé ou café peu sucré", "dejeuner": "légumes cuits, viande blanche ou poisson grillé, féculent en portion modérée, un fruit",
             "collation": "yaourt nature ou une poignée de fruits secs non salés", "diner": "soupe de légumes, œuf ou poisson, pain complet, laitage"}
    if f.get("heart_failure") or f.get("hypertension"):
        plan_type = "Hyposodé (pauvre en sel)"
        avoid += ["sel ajouté à table", "conserves, olives et fromages salés", "bouillons cubes, chips, biscuits apéritifs"]
        recommended += ["herbes, citron, ail et épices à la place du sel"]
        rules.append("régime hyposodé : " + ("insuffisance cardiaque" if f.get("heart_failure") else "hypertension artérielle"))
        if f.get("heart_failure"):
            hydration = 1500
            notes.append("Boissons : environ 1,5 litre par jour sauf consigne différente de votre médecin ; pesez-vous chaque matin.")
    if f.get("diabetes"):
        plan_type = "Contrôle glucidique" + (" et hyposodé" if "Hyposodé" in plan_type else "")
        avoid += ["sucre, pâtisseries, miel, confiture", "jus de fruits et sodas", "pain blanc en grande quantité"]
        recommended += ["féculents complets en portions régulières à chaque repas", "légumes verts à volonté"]
        meals["collation"] = "un fruit entier ou un yaourt nature sans sucre"
        rules.append("contrôle des glucides : diabète")
        notes.append("Ne sautez pas de repas, surtout si vous prenez de l'insuline ou un antidiabétique.")
    if f.get("renal"):
        avoid += ["excès de protéines animales", "bananes et fruits secs en grande quantité (potassium)"]
        rules.append("protéines et potassium modérés : atteinte rénale")
    if f.get("dysphagia"):
        plan_type += " — texture adaptée"
        avoid += ["aliments secs, friables ou à grains (riz sec, biscottes)", "liquides très fluides bus rapidement"]
        notes.append("Textures tendres ou mixées, petites bouchées, position assise, eau gélifiée si prescrite.")
        rules.append("texture adaptée : troubles de la déglutition")
    if f.get("ortho") or f.get("malnutrition") or f.get("osteoporosis") or age >= 70:
        recommended += ["protéines à chaque repas (œufs, poisson, volaille, laitages)", "laitages pour le calcium", "exposition douce au soleil (vitamine D)"]
        rules.append("apports en protéines, calcium et vitamine D : " + ("suites de chirurgie orthopédique" if f.get("ortho") else "prévention de la fonte musculaire"))
    if f.get("anemia"):
        recommended += ["aliments riches en fer (lentilles, viande rouge maigre, épinards) avec un fruit riche en vitamine C"]
        avoid += ["thé ou café pendant les repas (gêne l'absorption du fer)"]
        rules.append("apports en fer : anémie")
    if f.get("anticoagulant"):
        notes.append("Traitement anticoagulant : gardez une alimentation régulière, évitez l'alcool et ne prenez aucun complément ou plante sans avis médical.")
        rules.append("régularité alimentaire : anticoagulant")
    if f.get("copd"):
        recommended += ["repas fractionnés (5 petits repas)"]
        rules.append("repas fractionnés : gêne respiratoire")
    nutrition = {"plan_type": plan_type, "recommended_foods": list(dict.fromkeys(recommended)), "foods_to_avoid": list(dict.fromkeys(avoid)), "meals": meals,
                 "hydration_ml_daily": hydration, "calories_target": calories, "notes": " ".join(notes) or None, "rules": rules or ["alimentation équilibrée (aucune pathologie imposant un régime particulier trouvée)"],
                 "confidence": 0.8 if rules else 0.6, "source": src}

    # activité
    contraindications: list[str] = []
    name, kind, minutes, intensity, per_week = "Marche à allure confortable", "WALKING", 30, "MODERATE", 5
    days = ["Lundi", "Mardi", "Jeudi", "Vendredi", "Dimanche"]
    instructions = ["Échauffez-vous 5 minutes, arrêtez-vous en cas de douleur, d'essoufflement inhabituel, de vertige ou de palpitations."]
    act_rules: list[str] = []
    if age >= 70 or f.get("fall_risk"):
        minutes, intensity = 20, "LIGHT"
        contraindications += ["terrains glissants ou irréguliers", "activité seul(e) sans téléphone à portée de main"]
        instructions.append("Chaussures fermées, appui stable ; exercices d'équilibre près d'un support.")
        act_rules.append("intensité légère et prévention des chutes : " + ("âge ≥ 70 ans" if age >= 70 else "risque de chute"))
    if f.get("ortho"):
        name, minutes, intensity, per_week = "Marche progressive avec aide technique et exercices de rééducation", 15, "LIGHT", 7
        days = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        contraindications += ["course, sauts, sports de contact", "port de charges lourdes", "flexion forcée ou croisement des jambes (prothèse de hanche) — selon les consignes du chirurgien"]
        instructions.append("Plusieurs courtes marches par jour ; suivez le programme du kinésithérapeute et les consignes d'appui du chirurgien.")
        act_rules.append("reprise progressive : suites de chirurgie orthopédique")
    if f.get("heart_failure") or f.get("afib"):
        intensity = "LIGHT"
        minutes = min(minutes, 20)
        contraindications += ["efforts intenses ou en apnée", "activité en cas de prise de poids rapide, d'œdèmes ou d'essoufflement au repos"]
        instructions.append("Vous devez pouvoir parler pendant l'effort ; fractionnez si besoin.")
        act_rules.append("effort léger et fractionné : pathologie cardiaque")
    if f.get("copd"):
        intensity = "LIGHT"
        instructions.append("Respiration lèvres pincées ; gardez votre traitement inhalé à portée de main.")
        contraindications += ["effort par temps très froid, très chaud ou pollué"]
        act_rules.append("effort adapté au souffle : BPCO")
    if f.get("diabetes"):
        instructions.append("Contrôlez votre glycémie avant l'effort et gardez un sucre rapide sur vous.")
        act_rules.append("prévention de l'hypoglycémie : diabète")
    if f.get("anticoagulant"):
        contraindications += ["sports avec risque de choc ou de chute (anticoagulant)"]
        act_rules.append("éviter les chocs : anticoagulant")
    if f.get("epilepsy"):
        contraindications += ["natation ou baignade seul(e)", "activités en hauteur"]
        act_rules.append("sécurité : épilepsie")
    activity = {"activity_name": name, "activity_type": kind, "duration_minutes": minutes, "intensity": intensity, "frequency_per_week": per_week, "scheduled_days": days,
                "instructions": " ".join(instructions), "contraindications": list(dict.fromkeys(contraindications)), "rules": act_rules or ["activité d'endurance douce recommandée à tout adulte"],
                "confidence": 0.75 if act_rules else 0.6, "source": src}

    # habitudes
    habits = [
        {"key": "sleep", "category": "sleep", "title": "Sommeil régulier", "detail": "Couchez-vous et levez-vous à heures fixes ; 7 à 8 heures par nuit, écrans éteints 30 minutes avant.", "confidence": 0.7, "source": "recommandation générale"},
        {"key": "tobacco", "category": "tobacco", "title": "Pas de tabac", "detail": "Si vous fumez, parlez-en à votre médecin : un accompagnement à l'arrêt existe. Évitez aussi la fumée des autres.", "confidence": 0.8, "source": "recommandation générale"},
        {"key": "alcohol", "category": "alcohol", "title": "Alcool", "detail": ("Évitez l'alcool pendant votre traitement." if (f.get("anticoagulant") or f.get("heart_failure") or f.get("diabetes") or f.get("epilepsy")) else "Limitez l'alcool ; pas d'alcool avec vos médicaments sans avis médical."),
         "confidence": 0.8 if f.get("anticoagulant") else 0.7, "source": src if f.get("anticoagulant") else "recommandation générale"},
    ]
    if f.get("heart_failure"):
        habits.append({"key": "weight", "category": "monitoring", "title": "Poids chaque matin", "detail": "Pesez-vous au lever, après être allé(e) aux toilettes. Plus de 2 kg en 3 jours : appelez votre médecin.", "confidence": 0.85, "source": src})
    if f.get("hypertension") or f.get("heart_failure") or f.get("afib"):
        habits.append({"key": "bp", "category": "monitoring", "title": "Tension artérielle", "detail": "Mesurez votre tension assis(e), au calme, le matin et le soir, 3 jours avant chaque consultation ; notez les valeurs.", "confidence": 0.8, "source": src})
    if f.get("diabetes"):
        habits.append({"key": "glucose", "category": "monitoring", "title": "Glycémie", "detail": "Mesurez votre glycémie aux moments indiqués par votre médecin et notez les valeurs ; inspectez vos pieds chaque jour.", "confidence": 0.85, "source": src})
    if f.get("ortho"):
        habits.append({"key": "wound", "category": "monitoring", "title": "Cicatrice et douleur", "detail": "Surveillez la cicatrice (rougeur, chaleur, écoulement) et signalez toute fièvre ou douleur du mollet.", "confidence": 0.8, "source": src})
    if f.get("anticoagulant"):
        habits.append({"key": "bleeding", "category": "monitoring", "title": "Saignements", "detail": "Signalez tout saignement inhabituel (gencives, nez, urines, selles noires, bleus importants).", "confidence": 0.85, "source": src})
    for i, text in enumerate(params.get("doctor_instructions") or []):
        habits.append({"key": f"doctor_{i}", "category": "other", "title": "Consigne de votre médecin", "detail": text, "confidence": 0.95, "source": src})
    return {"nutrition": nutrition, "activity": activity, "habits": habits, "warnings": []}


def apply_guardrails(plan: dict[str, Any], params: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Garde-fous obligatoires, appliqués à TOUT plan (LLM ou règles) : allergies, régime cohérent avec la pathologie,
    aucune activité contre-indiquée, aucun médicament dans les conseils. Renvoie (plan corrigé, corrections faites)."""
    f, fixes = params.get("flags") or {}, []
    base = rule_based_plan(params)
    nut = dict(plan.get("nutrition") or base["nutrition"])
    act = dict(plan.get("activity") or base["activity"])
    habits = [h for h in (plan.get("habits") or base["habits"]) if isinstance(h, dict) and h.get("title")]
    # a) allergies : aucun aliment recommandé ne contient un allergène du patient
    banned: list[str] = []
    for allergy in params.get("allergies") or []:
        a = allergy.lower()
        for key, words in ALLERGEN_FOODS.items():
            if key in a:
                banned += list(words)
        banned.append(a.split("(")[0].strip())
    banned = [b for b in dict.fromkeys(banned) if len(b) >= 3]
    kept = [x for x in (nut.get("recommended_foods") or []) if not any(b in str(x).lower() for b in banned)]
    if len(kept) != len(nut.get("recommended_foods") or []):
        fixes.append("aliments retirés pour allergie : " + ", ".join(x for x in nut["recommended_foods"] if x not in kept))
    nut["recommended_foods"] = kept
    if nut.get("meals"):
        nut["meals"] = {k: v for k, v in nut["meals"].items() if not any(b in str(v).lower() for b in banned)} or None
    # b) régime cohérent avec la pathologie : les interdits des règles sont toujours présents
    must_avoid = base["nutrition"]["foods_to_avoid"]
    missing = [x for x in must_avoid if x not in (nut.get("foods_to_avoid") or [])]
    if (f.get("heart_failure") or f.get("hypertension") or f.get("diabetes") or f.get("dysphagia") or f.get("renal")) and missing:
        nut["foods_to_avoid"] = list(dict.fromkeys((nut.get("foods_to_avoid") or []) + missing))
        fixes.append("interdits alimentaires liés à la pathologie ajoutés")
    if (f.get("heart_failure") or f.get("hypertension")) and "hyposod" not in str(nut.get("plan_type", "")).lower():
        nut["plan_type"] = base["nutrition"]["plan_type"]
        fixes.append("régime ramené à hyposodé")
    if f.get("diabetes") and "glucid" not in str(nut.get("plan_type", "")).lower():
        nut["plan_type"] = base["nutrition"]["plan_type"]
        fixes.append("contrôle glucidique imposé")
    if f.get("heart_failure") and (nut.get("hydration_ml_daily") or 0) > 2000:
        nut["hydration_ml_daily"] = 1500
        fixes.append("hydratation ramenée à 1,5 L (insuffisance cardiaque)")
    nut["rules"] = list(dict.fromkeys((nut.get("rules") or []) + base["nutrition"]["rules"]))
    # c) activité : jamais plus intense ni plus longue que la limite des règles ; contre-indications toujours listées
    order = {"LIGHT": 0, "MODERATE": 1, "VIGOROUS": 2}
    limit = base["activity"]
    if order.get(str(act.get("intensity", "")).upper(), 1) > order[limit["intensity"]]:
        act["intensity"] = limit["intensity"]
        fixes.append("intensité de l'activité abaissée")
    if (act.get("duration_minutes") or 0) > limit["duration_minutes"] * 2:
        act["duration_minutes"] = limit["duration_minutes"]
        fixes.append("durée de l'activité abaissée")
    risky = ("course", "running", "saut", "contact", "muscu", "haltér", "boxe", "football", "natation") if (f.get("ortho") or f.get("heart_failure") or f.get("epilepsy") or (params.get("age") or 0) >= 70) else ()
    if any(w in str(act.get("activity_name", "")).lower() for w in risky):
        act.update(activity_name=limit["activity_name"], activity_type=limit["activity_type"])
        fixes.append("activité contre-indiquée remplacée")
    if str(act.get("activity_type", "")).upper() not in ("WALKING", "RUNNING", "SWIMMING", "CYCLING", "YOGA", "STRETCHING", "OTHER"):
        act["activity_type"] = "OTHER"
    act["contraindications"] = list(dict.fromkeys((act.get("contraindications") or []) + limit["contraindications"]))
    # d) aucun conseil ne parle de modifier un médicament
    forbidden = re.compile(r"\b(arr[êe]te[rz]?|augmente[rz]?|diminue[rz]?|double[rz]?|saute[rz]?|rempla[cç]e[rz]?)\b.{0,40}\b(m[ée]dicament|traitement|dose|comprim[ée]|insuline)", re.I)
    clean = [h for h in habits if not forbidden.search(str(h.get("detail", "")) + " " + str(h.get("title", "")))]
    if len(clean) != len(habits):
        fixes.append("conseil touchant au traitement retiré")
    for text_key in ("notes",):
        if nut.get(text_key) and forbidden.search(str(nut[text_key])):
            nut[text_key] = base["nutrition"]["notes"]
            fixes.append("note alimentaire touchant au traitement remplacée")
    keys = {h.get("key") for h in clean}
    for h in base["habits"]:  # auto-surveillance imposée par la pathologie et consignes du médecin : toujours présentes
        if h["key"] not in keys and (h["category"] == "monitoring" or h["key"].startswith("doctor_")):
            clean.append(h)
    for item in [nut, act, *clean]:
        try:
            item["confidence"] = max(0.0, min(1.0, float(item.get("confidence", 0.6))))
        except (TypeError, ValueError):
            item["confidence"] = 0.6
        item.setdefault("source", source_line(params))
    return {"nutrition": nut, "activity": act, "habits": clean, "warnings": list(plan.get("warnings") or [])}, fixes


LLM_SYSTEM = """Tu es un assistant d'éducation thérapeutique. À partir des paramètres cliniques pseudonymisés d'un patient sorti d'hôpital,
propose un programme d'hygiène de vie : alimentation, activité physique, habitudes. Règles absolues : tu ne proposes, ne modifies et ne
commentes JAMAIS un médicament, une dose ou un horaire ; tu respectes les allergies, la pathologie (hyposodé si insuffisance cardiaque ou
hypertension, contrôle glucidique si diabète, texture adaptée si troubles de déglutition) et les consignes du médecin ; aucune activité
contre-indiquée. Réponds UNIQUEMENT par un objet JSON : {"nutrition": {"plan_type", "recommended_foods": [], "foods_to_avoid": [],
"meals": {"petit_dejeuner", "dejeuner", "collation", "diner"}, "hydration_ml_daily", "calories_target", "notes", "confidence"},
"activity": {"activity_name", "activity_type" (WALKING|CYCLING|YOGA|STRETCHING|SWIMMING|OTHER), "duration_minutes", "intensity" (LIGHT|MODERATE),
"frequency_per_week", "scheduled_days": [], "instructions", "contraindications": [], "confidence"},
"habits": [{"key", "category" (sleep|tobacco|alcohol|monitoring|other), "title", "detail", "confidence"}]}. Confiance entre 0 et 1. Français simple."""


async def llm_plan(params: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Plan proposé par le LLM (données pseudonymisées). None si le LLM est désactivé, indisponible ou répond mal."""
    if not settings.CARE_AGENT_USE_LLM or not settings.ANTHROPIC_API_KEY:
        return None
    from app.services.companion import _anthropic

    safe = {k: params.get(k) for k in ("age", "gender", "conditions", "admission_reasons", "allergies", "flags", "vitals", "doctor_instructions")}
    safe["traitements_en_cours_pour_information_seulement"] = [m["name"] for m in params.get("medications", [])]
    try:
        raw = await _anthropic(settings.CHAT_MODEL, LLM_SYSTEM, [{"role": "user", "content": json.dumps(safe, ensure_ascii=False)}], 1800)
        match = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(match.group(0)) if match else None
        return data if isinstance(data, dict) and isinstance(data.get("nutrition"), dict) and isinstance(data.get("activity"), dict) else None
    except Exception as exc:
        logger.warning("care agent llm unavailable category=%s", type(exc).__name__)
        return None


# ── 5. suivi de l'observance ─────────────────────────────────────────────────
TAKEN = (DoseStatus.TAKEN_ON_TIME, DoseStatus.TAKEN_LATE)


def is_critical(name: str) -> bool:
    return _has((name or "").lower(), CRITICAL_MEDS)


def adherence_from_doses(doses: list[tuple[str, date, time, Any]], now: datetime) -> dict[str, Any]:
    """`doses` : (médicament, date, heure, statut). Calcule l'observance sur 7 jours et la plus longue série de prises
    manquées consécutives par médicament (une prise prévue depuis plus de 2 h et non prise est manquée)."""
    by_med: dict[str, list[tuple[datetime, bool]]] = {}
    taken = due = 0
    for name, d, t, status in doses:
        at = datetime.combine(d, t)
        if status == DoseStatus.CANCELLED or at > now:
            continue
        ok = status in TAKEN
        missed = status == DoseStatus.MISSED or (not ok and now - at > timedelta(hours=2))
        if not ok and not missed:
            continue
        by_med.setdefault(name, []).append((at, ok))
        if now - at <= timedelta(days=7):
            due += 1
            taken += int(ok)
    streaks = {}
    for name, rows in by_med.items():
        rows.sort(key=lambda r: r[0], reverse=True)
        n = 0
        for _, ok in rows:
            if ok:
                break
            n += 1
        streaks[name] = n
    rate = round(taken / due, 2) if due else None
    worst = max(streaks.items(), key=lambda kv: kv[1]) if streaks else ("", 0)
    critical = [name for name, n in streaks.items() if n >= 3 and is_critical(name)]
    if rate is None:
        message = "Votre calendrier de prises est prêt. Cochez chaque prise : cela aide votre médecin à vous suivre."
    elif rate >= 0.9:
        message = "Bravo, vous suivez très bien votre traitement cette semaine. Continuez ainsi !"
    elif rate >= 0.7:
        message = "Vous suivez bien votre traitement. Quelques prises ont été oubliées : un rappel un peu plus tôt peut aider."
    else:
        message = "Plusieurs prises ont été oubliées cette semaine. Reprenons pas à pas : commencez par la prochaine prise, et parlez-en à votre médecin si c'est difficile."
    return {"rate_7d": rate, "taken_7d": taken, "due_7d": due, "missed_streak": worst[1], "missed_streak_medication": worst[0] if worst[1] else None, "critical_missed": critical, "message": message}


async def adherence(db: AsyncSession, patient_id: uuid.UUID, now: Optional[datetime] = None) -> dict[str, Any]:
    from app.services.dose_status import patient_now

    patient = (await db.execute(select(Patient).where(Patient.id == patient_id))).scalar_one_or_none()
    local = (now or patient_now(patient)).replace(tzinfo=None)
    rows = (await db.execute(
        select(PrescriptionItem.medication_name, MedicationDose.scheduled_date, MedicationDose.scheduled_time, MedicationDose.status)
        .join(PrescriptionItem, PrescriptionItem.id == MedicationDose.prescription_item_id)
        .where(MedicationDose.patient_id == patient_id, MedicationDose.scheduled_date >= local.date() - timedelta(days=14), MedicationDose.scheduled_date <= local.date())
    )).all()
    return adherence_from_doses([(r[0], r[1], r[2], r[3]) for r in rows], local)


# ── exécution ────────────────────────────────────────────────────────────────
class Steps(list):
    def add(self, name: str, status: str, detail: str) -> None:
        self.append({"name": name, "status": status, "detail": detail[:600]})


async def current_program(db: AsyncSession, patient_id: uuid.UUID) -> Optional[CareProgram]:
    return (await db.execute(select(CareProgram).where(CareProgram.patient_id == patient_id, CareProgram.is_current.is_(True)).order_by(CareProgram.generated_at.desc()).limit(1))).scalar_one_or_none()


def _report_payload(patient_id: uuid.UUID, params: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Programme → brouillon `DOCTOR_REPORT` du pipeline existant (crée `NutritionPlan` et `SportPlan` à l'application)."""
    nut, act = plan["nutrition"], plan["activity"]
    return {
        "patient_id": str(patient_id), "motif_consultation": "; ".join(params.get("admission_reasons") or []) or None,
        "diagnostic": "; ".join(params.get("conditions") or [])[:800] or None, "conclusion": None,
        "objectifs_traitement": [h["title"] for h in plan["habits"] if h.get("category") == "monitoring"],
        "precautions": act.get("contraindications") or [], "alertes": [f"Allergie : {a}" for a in params.get("allergies") or []], "dates_suivi": [],
        "sport": {"recommande": [act["activity_name"]], "a_eviter": act.get("contraindications") or [], "frequence": f"{act.get('frequency_per_week')} fois par semaine, {act.get('duration_minutes')} min",
                  "intensite": act.get("intensity"), "duree": f"{act.get('duration_minutes')} min", "restrictions": [act.get("instructions") or ""], "jours": act.get("scheduled_days") or []},
        "nutrition": {"a_privilegier": nut.get("recommended_foods") or [], "a_limiter": nut.get("foods_to_avoid") or [], "conseils": nut.get("notes"), "regime_type": nut.get("plan_type"),
                      "hydratation_ml": nut.get("hydration_ml_daily"), "calories_cible": nut.get("calories_target"), "repas": nut.get("meals")},
        "medicaments": [], "resume_patient": "Programme de vie proposé par le CarePlanAgent à partir de votre séjour. " + DISCLAIMER,
        "confidence_scores": {"nutrition": nut.get("confidence"), "sport": act.get("confidence")},
    }


async def apply_program(db: AsyncSession, program: CareProgram, validated_by: str, auto: bool = False) -> None:
    """Validation : applique le brouillon par le flux existant, puis remplace les anciens plans actifs par les nouveaux."""
    from app.api.automation import execute_apply_drafts
    from app.models.nutrition import NutritionPlan, NutritionPlanStatus
    from app.models.sport import PlanStatus, SportPlan

    if program.status == "applied":
        return
    old_n = [r[0] for r in (await db.execute(select(NutritionPlan.id).where(NutritionPlan.patient_id == program.patient_id, NutritionPlan.status == NutritionPlanStatus.ACTIVE))).all()]
    old_s = [r[0] for r in (await db.execute(select(SportPlan.id).where(SportPlan.patient_id == program.patient_id, SportPlan.status == PlanStatus.ACTIVE))).all()]
    if program.document_source_id:
        await execute_apply_drafts(ApplyPayload(document_source_ids=[program.document_source_id], confirmed_by=validated_by), db)
    if old_n:
        await db.execute(update(NutritionPlan).where(NutritionPlan.id.in_(old_n)).values(status=NutritionPlanStatus.COMPLETED))
    if old_s:
        await db.execute(update(SportPlan).where(SportPlan.id.in_(old_s)).values(status=PlanStatus.COMPLETED))
    act = (program.payload or {}).get("activity") or {}
    new_s = (await db.execute(select(SportPlan).where(SportPlan.patient_id == program.patient_id, SportPlan.status == PlanStatus.ACTIVE))).scalars().all()
    for s in new_s:  # le flux existant fixe des valeurs par défaut : on y remet celles du programme validé
        from app.models.sport import ActivityType, Intensity

        s.duration_minutes = act.get("duration_minutes") or s.duration_minutes
        s.frequency_per_week = act.get("frequency_per_week") or s.frequency_per_week
        try:
            s.intensity = Intensity(str(act.get("intensity", "MODERATE")).upper())
            s.activity_type = ActivityType(str(act.get("activity_type", "WALKING")).upper())
        except ValueError:
            pass
        s.instructions = act.get("instructions") or s.instructions
    program.status, program.auto_applied, program.validated_by, program.validated_at = "applied", auto, validated_by, datetime.utcnow()
    await db.commit()


def program_out(program: CareProgram, medications: dict[str, Any], adh: dict[str, Any]) -> dict[str, Any]:
    payload = program.payload or {}
    label = DRAFT_LABEL if program.status != "applied" else (AUTO_LABEL if program.auto_applied else DOCTOR_LABEL)
    return {"id": str(program.id), "generated_at": program.generated_at.isoformat() + "Z", "mode": program.mode, "fallback": bool(program.fallback),
            "validation": {"status": "applied" if program.status == "applied" else "draft", "auto_applied": bool(program.auto_applied), "label": label, "validated_by": program.validated_by},
            "source": program.source, "nutrition": payload.get("nutrition"), "activity": payload.get("activity"), "habits": payload.get("habits") or [],
            "medications": medications, "adherence": {"rate_7d": adh.get("rate_7d"), "missed_streak": adh.get("missed_streak", 0), "message": adh.get("message", "")},
            "warnings": payload.get("warnings") or [], "disclaimer": DISCLAIMER}


def run_out(run: AgentRun) -> dict[str, Any]:
    return {"id": str(run.id), "started_at": run.started_at.isoformat() + "Z", "trigger": run.trigger, "mode": run.mode, "status": run.status, "summary": run.summary or "",
            "steps": run.steps or [], "care_team_note": run.care_team_note, "duration_ms": run.duration_ms}


async def run(db: AsyncSession, patient: Patient, parsed: Optional[dict[str, Any]], trigger: str, rx_changed: bool = True, plan_changed: bool = True) -> AgentRun:
    """Une exécution complète de l'agent. `parsed` = Bundle hospitalier analysé (None : suivi d'observance seul)."""
    from app.api.automation import execute_apply_drafts

    started, steps = monotonic(), Steps()
    record = AgentRun(patient_id=patient.id, trigger=trigger, mode="rules", status="ok", started_at=datetime.utcnow())
    db.add(record)
    await db.flush()
    summary: list[str] = []
    try:
        params = None
        if parsed is not None:
            # 1. extraction
            params = extract_parameters(parsed, patient.allergies if isinstance(patient.allergies, list) else None)
            active = [k for k, v in params["flags"].items() if v]
            steps.add("extraction", "ok", f"{len(params['conditions'])} problème(s), {len(params['allergies'])} allergie(s), {len(params['medications'])} médicament(s) ({params['medication_origin']}), "
                                         f"{len(params['doctor_instructions'])} consigne(s) du médecin ; profils : {', '.join(active) or 'aucun'}")
            # 2. médicaments — déterministe
            if not params["medications"]:
                steps.add("medicaments", "skipped", "aucune ordonnance active dans les données hospitalières : aucun rappel créé")
            elif not rx_changed:
                steps.add("medicaments", "skipped", "ordonnance inchangée depuis la dernière synchronisation : calendrier conservé")
            else:
                payload, warnings = medication_payload(patient.id, parsed)
                doc = DocumentSource(patient_id=patient.id, document_type=DocumentType.PRESCRIPTION, status=DocumentStatus.DRAFT, original_filename=f"hospital-copilot:{params['pseudonym']}:ordonnance",
                                     extracted_data=payload, confidence_scores=payload["confidence_scores"])
                db.add(doc)
                await db.commit()
                signer = params.get("doctor") or "médecin hospitalier"
                result = await execute_apply_drafts(ApplyPayload(document_source_ids=[doc.id], confirmed_by=f"ordonnance signée — {signer}"), db)
                steps.add("medicaments", "ok", f"{len(payload['medicaments'])} médicament(s), {result.doses_generated} prise(s) planifiée(s) à partir de l'ordonnance signée, sans LLM"
                                              + (" ; " + " ".join(warnings) if warnings else ""))
                summary.append(f"{result.doses_generated} prises planifiées")
            # 3. programme de vie
            if not plan_changed and await current_program(db, patient.id):
                steps.add("programme", "skipped", "données cliniques inchangées : programme conservé")
            else:
                proposal = await llm_plan(params)
                fallback = proposal is None
                plan, fixes = apply_guardrails(proposal or rule_based_plan(params), params)
                record.mode = "rules" if fallback else "llm"
                reason = ("LLM désactivé ou clé absente" if not (settings.CARE_AGENT_USE_LLM and settings.ANTHROPIC_API_KEY) else "LLM indisponible") if fallback else ""
                steps.add("programme", "ok", (f"mode de secours par règles ({reason})" if fallback else "proposé par le LLM") + f" ; garde-fous : {'; '.join(fixes) or 'aucune correction nécessaire'}")
                report = DocumentSource(patient_id=patient.id, document_type=DocumentType.DOCTOR_REPORT, status=DocumentStatus.DRAFT, original_filename=f"hospital-copilot:{params['pseudonym']}:programme",
                                        extracted_data=_report_payload(patient.id, params, plan), confidence_scores={"nutrition": plan["nutrition"]["confidence"], "sport": plan["activity"]["confidence"]})
                db.add(report)
                await db.execute(update(CareProgram).where(CareProgram.patient_id == patient.id, CareProgram.is_current.is_(True)).values(is_current=False, status="superseded"))
                program = CareProgram(patient_id=patient.id, document_source_id=report.id, mode=record.mode, fallback=fallback, status="draft", source=source_line(params), parameters=params, payload=plan, is_current=True)
                db.add(program)
                await db.commit()
                # 4. validation
                if settings.DEMO_AUTO_APPLY:
                    await apply_program(db, program, AUTO_LABEL, auto=True)
                    steps.add("validation", "ok", AUTO_LABEL)
                else:
                    steps.add("validation", "ok", "programme en brouillon : en attente de validation par un médecin")
                summary.append("programme de vie " + ("appliqué (démonstration)" if settings.DEMO_AUTO_APPLY else "en brouillon"))
        # 5. suivi
        adh = await adherence(db, patient.id)
        detail = adh["message"] if adh["rate_7d"] is None else f"observance 7 jours : {round(adh['rate_7d'] * 100)} % ({adh['taken_7d']}/{adh['due_7d']}) ; plus longue série manquée : {adh['missed_streak']}"
        if adh["critical_missed"]:
            names = ", ".join(adh["critical_missed"])
            today_start = datetime.combine(date.today(), time.min)
            already = (await db.execute(select(Notification.id).where(Notification.user_id == patient.user_id, Notification.category == NotificationCategory.MEDICATION,
                                                                    Notification.title == "Prises manquées", Notification.created_at >= today_start))).first()
            if not already:
                db.add(Notification(user_id=patient.user_id, title="Prises manquées", category=NotificationCategory.MEDICATION, priority=NotificationPriority.HIGH,
                                    body=f"Vous avez manqué 3 prises de suite de {names}. Reprenez votre traitement à la prochaine prise prévue, sans doubler la dose, et contactez votre médecin.",
                                    data={"type": "ADHERENCE_ALERT", "medications": adh["critical_missed"]}))
            record.care_team_note = f"Patient {(params or {}).get('pseudonym') or ''} : 3 prises consécutives manquées ou plus pour {names} (médicament critique). Observance 7 jours : {round((adh['rate_7d'] or 0) * 100)} %. À rappeler."
            detail += f" ; ALERTE : {names} — patient notifié, signalement pour l'équipe soignante"
        steps.add("suivi", "ok", detail)
        record.summary = " · ".join(summary) or detail
    except Exception as exc:  # une erreur de l'agent ne doit jamais casser la synchronisation
        logger.exception("care agent failed")
        await db.rollback()
        record = await db.merge(record)
        steps.add("erreur", "error", f"{type(exc).__name__}: {exc}")
        record.status, record.summary = "error", f"Erreur de l'agent : {type(exc).__name__}"
    if record.status != "error" and any(s["status"] == "error" for s in steps):
        record.status = "partial"
    record.steps, record.finished_at, record.duration_ms = list(steps), datetime.utcnow(), int((monotonic() - started) * 1000)
    db.add(AuditLog(patient_id=patient.id, action="CARE_AGENT_RUN", entity_type="AgentRun", entity_id=record.id, performed_by="CarePlanAgent",
                    changes={"trigger": trigger, "mode": record.mode, "status": record.status, "steps": [f"{s['name']}:{s['status']}" for s in steps]}))
    await db.commit()
    return record
