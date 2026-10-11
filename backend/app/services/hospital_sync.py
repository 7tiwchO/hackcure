"""
Liaison et synchronisation avec Hospital Copilot.

- `link_patient` : vérifie (pseudonyme + date de naissance) auprès de l'hôpital, enregistre le lien avec le consentement
  explicite, lance la première synchronisation.
- `sync_patient` : récupère le Bundle FHIR `$everything`, le garde en cache (disponible hors ligne), enregistre les
  documents comme `DocumentSource` avec la date de synchronisation, puis lance le CarePlanAgent si l'ordonnance ou les
  données cliniques ont changé.
- `periodic_sync_loop` : tâche de fond optionnelle (`HOSPITAL_SYNC_INTERVAL_MINUTES` > 0).
- Abonnement : le lien et l'agent exigent un abonnement actif (`require_subscription`).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import care_plan_agent
from app.config import settings
from app.integrations import hospital_copilot as hc
from app.models.audit_log import AuditLog
from app.models.document_source import DocumentSource, DocumentStatus, DocumentType
from app.models.hospital_link import AgentRun, HospitalLink, Subscription, SubscriptionStatus
from app.models.patient import Patient

logger = logging.getLogger(__name__)

PLANS = {"monthly": {"days": 30, "price_tnd": 29.0, "label": "Mensuel"}, "quarterly": {"days": 90, "price_tnd": 75.0, "label": "Trimestriel"}}


class LinkError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


# ── abonnement ───────────────────────────────────────────────────────────────
async def current_subscription(db: AsyncSession, patient_id: uuid.UUID) -> Optional[Subscription]:
    sub = (await db.execute(select(Subscription).where(Subscription.patient_id == patient_id).order_by(Subscription.end_date.desc()).limit(1))).scalar_one_or_none()
    if sub and sub.status == SubscriptionStatus.ACTIVE.value and sub.end_date < date.today():
        sub.status = SubscriptionStatus.EXPIRED.value
        await db.commit()
    return sub


def subscription_out(sub: Optional[Subscription]) -> dict[str, Any]:
    share = float(settings.SUBSCRIPTION_HOSPITAL_SHARE_PCT)
    if not sub:
        return {"status": "none", "active": False, "plan": None, "hospital_name": settings.HOSPITAL_NAME, "start_date": None, "end_date": None, "price_tnd": None,
                "hospital_share_pct": share, "team_share_pct": round(100 - share, 2), "demo": True, "plans": PLANS}
    active = sub.status == SubscriptionStatus.ACTIVE.value and sub.end_date >= date.today()
    return {"status": "active" if active else "expired", "active": active, "plan": sub.plan, "hospital_name": sub.hospital_name, "start_date": sub.start_date.isoformat(),
            "end_date": sub.end_date.isoformat(), "price_tnd": sub.price_tnd, "hospital_share_pct": sub.hospital_share_pct, "team_share_pct": sub.team_share_pct, "demo": bool(sub.demo), "plans": PLANS}


async def activate_subscription(db: AsyncSession, patient_id: uuid.UUID, plan: str) -> Subscription:
    """Activation de démonstration : aucun paiement. Le partage de revenus vient de la configuration."""
    if plan not in PLANS:
        raise LinkError(400, "Formule inconnue (monthly ou quarterly)")
    share = max(0.0, min(100.0, float(settings.SUBSCRIPTION_HOSPITAL_SHARE_PCT)))
    sub = Subscription(patient_id=patient_id, hospital_name=settings.HOSPITAL_NAME, plan=plan, start_date=date.today(), end_date=date.today() + timedelta(days=PLANS[plan]["days"]),
                       status=SubscriptionStatus.ACTIVE.value, price_tnd=PLANS[plan]["price_tnd"], hospital_share_pct=share, team_share_pct=round(100 - share, 2), demo=True)
    db.add(sub)
    db.add(AuditLog(patient_id=patient_id, action="SUBSCRIPTION_ACTIVATED", entity_type="Subscription", performed_by="patient", changes={"plan": plan, "demo": True, "hospital_share_pct": share}))
    await db.commit()
    return sub


async def subscription_active(db: AsyncSession, patient_id: uuid.UUID) -> bool:
    return subscription_out(await current_subscription(db, patient_id))["active"]


# ── lien ─────────────────────────────────────────────────────────────────────
async def get_link(db: AsyncSession, patient_id: uuid.UUID) -> Optional[HospitalLink]:
    link = (await db.execute(select(HospitalLink).where(HospitalLink.patient_id == patient_id))).scalar_one_or_none()
    return link if link and link.revoked_at is None else None


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() + "Z" if value else None


async def link_status(db: AsyncSession, patient_id: uuid.UUID) -> dict[str, Any]:
    link = await get_link(db, patient_id)
    active = await subscription_active(db, patient_id)
    if not link:
        return {"linked": False, "pseudonym": None, "linked_at": None, "consent_at": None, "last_sync_at": None, "last_sync_status": None, "last_sync_error": None,
                "documents": [], "subscription_active": active, "last_agent_run": None, "hospital_configured": hc.configured()}
    rows = (await db.execute(select(DocumentSource).where(DocumentSource.patient_id == patient_id, DocumentSource.original_filename.like(f"hospital-copilot:{link.pseudonym}:%"))
                             .order_by(DocumentSource.created_at.desc()).limit(300))).scalars().all()
    latest: dict[str, DocumentSource] = {}
    for d in rows:  # un document par origine (la dernière version de l'ordonnance, du programme, de chaque rapport)
        latest.setdefault(d.original_filename, d)
    docs = sorted(latest.values(), key=lambda d: d.updated_at or d.created_at, reverse=True)[:12]
    run = (await db.execute(select(AgentRun).where(AgentRun.patient_id == patient_id).order_by(AgentRun.started_at.desc()).limit(1))).scalar_one_or_none()
    titles = {"ordonnance": "Ordonnance (médicaments et horaires)", "programme": "Programme de vie proposé", "dossier": "Dossier médical (problèmes, allergies, constantes)"}
    out = []
    for d in docs:
        key = (d.original_filename or "").rsplit(":", 1)[-1]
        meta = (d.extracted_data or {}).get("_hospital") or {}
        out.append({"id": str(d.id), "type": d.document_type.value if d.document_type else "", "title": meta.get("title") or titles.get(key.split("#")[0], "Document hospitalier"),
                    "date": meta.get("date"), "status": d.status.value if d.status else "", "synced_at": _iso(d.updated_at or d.created_at)})
    return {"linked": True, "pseudonym": link.pseudonym, "linked_at": _iso(link.linked_at), "consent_at": _iso(link.consent_at), "last_sync_at": _iso(link.last_sync_at),
            "last_sync_status": link.last_sync_status, "last_sync_error": link.last_sync_error, "documents": out, "subscription_active": active,
            "last_agent_run": care_plan_agent.run_out(run) if run else None, "hospital_configured": hc.configured()}


async def link_patient(db: AsyncSession, patient: Patient, pseudonym: str, birth_date: date, consent: bool, client: Optional[hc.HospitalCopilotClient] = None) -> dict[str, Any]:
    if not consent:
        raise LinkError(400, "Votre consentement explicite est nécessaire pour lier votre dossier hospitalier.")
    pseudo = hc.normalize_pseudonym(pseudonym)
    if not hc.PSEUDONYM_RE.match(pseudo):
        raise LinkError(400, "Identifiant de séjour invalide (format attendu : PAT-0000).")
    if not await subscription_active(db, patient.id):
        raise LinkError(402, "Un abonnement actif est nécessaire pour lier votre dossier hospitalier.")
    client = client or hc.HospitalCopilotClient()
    try:
        ok = await client.verify_identity(pseudo, birth_date)
    except hc.HospitalRejected as exc:
        if exc.status == 404:
            raise LinkError(404, "Aucun séjour ne correspond à cet identifiant et à cette date de naissance.")
        raise LinkError(503, "La plateforme hospitalière a refusé la demande (jeton de service à vérifier).")
    except hc.HospitalUnavailable:
        raise LinkError(503, "La plateforme hospitalière est injoignable pour le moment. Réessayez plus tard.")
    if not ok:  # même message que « inconnu » : on ne révèle pas qu'un pseudonyme existe
        raise LinkError(404, "Aucun séjour ne correspond à cet identifiant et à cette date de naissance.")
    other = (await db.execute(select(HospitalLink).where(HospitalLink.pseudonym == pseudo, HospitalLink.patient_id != patient.id, HospitalLink.revoked_at.is_(None)))).scalar_one_or_none()
    if other:
        raise LinkError(409, "Ce séjour est déjà lié à un autre compte.")
    link = (await db.execute(select(HospitalLink).where(HospitalLink.patient_id == patient.id))).scalar_one_or_none()
    now = datetime.utcnow()
    if link:
        link.pseudonym, link.consent_at, link.linked_at, link.revoked_at, link.hospital_url = pseudo, now, now, None, client.base_url
        link.cached_bundle, link.cached_digest, link.rx_digest = None, None, None
    else:
        link = HospitalLink(patient_id=patient.id, pseudonym=pseudo, consent_at=now, linked_at=now, hospital_url=client.base_url)
        db.add(link)
    db.add(AuditLog(patient_id=patient.id, action="HOSPITAL_LINK_CREATED", entity_type="HospitalLink", performed_by="patient", changes={"pseudonym": pseudo, "consent": True}))
    await db.commit()
    await sync_patient(db, patient, trigger="link", client=client)
    return await link_status(db, patient.id)


async def unlink_patient(db: AsyncSession, patient: Patient) -> None:
    """Retrait du consentement : le lien est révoqué et le cache hospitalier effacé (les prises déjà planifiées restent)."""
    link = await get_link(db, patient.id)
    if link:
        link.revoked_at, link.cached_bundle, link.cached_digest, link.rx_digest = datetime.utcnow(), None, None, None
        db.add(AuditLog(patient_id=patient.id, action="HOSPITAL_LINK_REVOKED", entity_type="HospitalLink", performed_by="patient"))
        await db.commit()


def _rx_digest(parsed: dict[str, Any]) -> str:
    meds, _ = hc.discharge_medications(parsed)
    slim = sorted(json.dumps({k: m.get(k) for k in ("name", "dose", "times", "per_day", "duration_days", "category")}, sort_keys=True, ensure_ascii=False) for m in meds)
    return hashlib.sha256("\n".join(slim).encode("utf-8")).hexdigest()


async def _store_documents(db: AsyncSession, patient: Patient, link: HospitalLink, parsed: dict[str, Any]) -> int:
    """Rapports et dossier reçus → `DocumentSource` (une ligne par document hospitalier, mise à jour à chaque synchronisation)."""
    n = 0
    record = {"conditions": parsed["conditions"], "allergies": parsed["allergies"], "vitals": parsed["vitals"], "encounters": parsed["encounters"], "labs": parsed["labs"][:40], "psych": parsed.get("psych")}
    items = [(f"hospital-copilot:{link.pseudonym}:dossier", DocumentType.MEDICAL_RECORD, {"_hospital": {"title": "Dossier médical (problèmes, allergies, constantes)", "date": date.today().isoformat()}, **record})]
    for d in parsed["documents"]:
        kind = ("Rapport de sortie" if d["kind"] == "discharge" else "Rapport médical") if d.get("current_stay") else "Compte rendu d'un séjour antérieur"
        title = kind + (f" — {d['author']}" if d.get("author") else "")
        items.append((f"hospital-copilot:{link.pseudonym}:rapport#{d['id']}", DocumentType.DOCTOR_REPORT, {"_hospital": {"title": title, "date": d.get("date"), "kind": d["kind"], "author": d.get("author")}, "texte_brut": d.get("text", "")[:20000]}))
    for name, dtype, data in items:
        row = (await db.execute(select(DocumentSource).where(DocumentSource.patient_id == patient.id, DocumentSource.original_filename == name))).scalar_one_or_none()
        if row:
            row.extracted_data, row.updated_at = data, datetime.utcnow()
        else:
            db.add(DocumentSource(patient_id=patient.id, document_type=dtype, status=DocumentStatus.CONFIRMED, original_filename=name, extracted_data=data))
        n += 1
    return n


async def sync_patient(db: AsyncSession, patient: Patient, trigger: str = "sync", client: Optional[hc.HospitalCopilotClient] = None) -> dict[str, Any]:
    link = await get_link(db, patient.id)
    if not link:
        raise LinkError(404, "Aucun dossier hospitalier lié.")
    if not await subscription_active(db, patient.id):
        raise LinkError(402, "Un abonnement actif est nécessaire pour synchroniser votre dossier hospitalier.")
    client = client or hc.HospitalCopilotClient()
    link.last_attempt_at = datetime.utcnow()
    try:
        bundle = await client.everything(link.pseudonym)
    except hc.HospitalUnavailable as exc:
        link.last_sync_status, link.last_sync_error = "offline", f"Plateforme hospitalière injoignable ({exc}). Dernière synchronisation conservée."
        await db.commit()
        if link.cached_bundle and not await care_plan_agent.current_program(db, patient.id):  # hors ligne mais cache présent et rien de généré : l'agent travaille sur le cache
            await care_plan_agent.run(db, patient, hc.parse_bundle(link.cached_bundle), trigger=f"{trigger}-cache")
        else:
            await care_plan_agent.run(db, patient, None, trigger=f"{trigger}-offline")
        return await link_status(db, patient.id)
    except hc.HospitalRejected as exc:
        link.last_sync_status, link.last_sync_error = "error", f"Refus de la plateforme hospitalière ({exc.status})."
        await db.commit()
        return await link_status(db, patient.id)
    parsed = hc.parse_bundle(bundle)
    digest, rx = hc.bundle_digest(bundle), _rx_digest(parsed)
    plan_changed, rx_changed = digest != link.cached_digest, rx != link.rx_digest
    link.cached_bundle, link.cached_digest, link.rx_digest = bundle, digest, rx
    link.last_sync_at, link.last_sync_status, link.last_sync_error = datetime.utcnow(), "ok", None
    count = await _store_documents(db, patient, link, parsed)
    db.add(AuditLog(patient_id=patient.id, action="HOSPITAL_SYNC", entity_type="HospitalLink", entity_id=link.id, performed_by=trigger,
                    changes={"resources": len(bundle.get("entry") or []), "documents": count, "rx_changed": rx_changed, "plan_changed": plan_changed}))
    await db.commit()
    await care_plan_agent.run(db, patient, parsed, trigger=trigger, rx_changed=rx_changed, plan_changed=plan_changed)
    return await link_status(db, patient.id)


async def periodic_sync_loop() -> None:
    """Synchronisation périodique de tous les liens actifs (désactivée si HOSPITAL_SYNC_INTERVAL_MINUTES = 0)."""
    from app.database import AsyncSessionLocal

    interval = max(1.0, float(settings.HOSPITAL_SYNC_INTERVAL_MINUTES)) * 60
    while True:
        await asyncio.sleep(interval)
        try:
            async with AsyncSessionLocal() as db:
                links = (await db.execute(select(HospitalLink).where(HospitalLink.revoked_at.is_(None)))).scalars().all()
                for link in links:
                    patient = (await db.execute(select(Patient).where(Patient.id == link.patient_id))).scalar_one_or_none()
                    if patient and await subscription_active(db, patient.id):
                        await sync_patient(db, patient, trigger="periodic")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("periodic hospital sync failed")
