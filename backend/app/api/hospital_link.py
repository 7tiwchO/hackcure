"""Lien hospitalier, programme de vie, journal du CarePlanAgent et abonnement (API du patient)."""
from datetime import date, datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import care_plan_agent
from app.database import get_db
from app.dependencies import get_current_user
from app.models.dose import DoseStatus, MedicationDose
from app.models.hospital_link import AgentRun, CareProgram
from app.models.medication import PrescriptionItem
from app.models.patient import Patient
from app.models.prescription import Prescription
from app.models.user import User, UserRole
from app.services import hospital_sync
from app.services.dose_status import patient_now

router = APIRouter(prefix="/api", tags=["Hospital link & care program"])


async def current_patient(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> Patient:
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Patient account required")
    patient = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
    return patient


class LinkRequest(BaseModel):
    pseudonym: str = Field(min_length=4, max_length=40)
    date_of_birth: date
    consent: bool = False


def _raise(exc: hospital_sync.LinkError) -> None:
    raise HTTPException(status_code=exc.status, detail=exc.detail)


# ── lien hospitalier ─────────────────────────────────────────────────────────
@router.get("/hospital-link")
async def get_hospital_link(patient: Patient = Depends(current_patient), db: AsyncSession = Depends(get_db)):
    return await hospital_sync.link_status(db, patient.id)


@router.post("/hospital-link")
async def create_hospital_link(body: LinkRequest, patient: Patient = Depends(current_patient), db: AsyncSession = Depends(get_db)):
    """Lie le compte au séjour hospitalier (pseudonyme + date de naissance, consentement explicite) puis synchronise."""
    try:
        return await hospital_sync.link_patient(db, patient, body.pseudonym, body.date_of_birth, body.consent)
    except hospital_sync.LinkError as exc:
        _raise(exc)


@router.post("/hospital-link/sync")
async def sync_hospital_link(patient: Patient = Depends(current_patient), db: AsyncSession = Depends(get_db)):
    """Synchronisation manuelle. Hors ligne : renvoie le dernier état conservé (`last_sync_status = offline`)."""
    try:
        return await hospital_sync.sync_patient(db, patient, trigger="sync")
    except hospital_sync.LinkError as exc:
        _raise(exc)


@router.delete("/hospital-link")
async def delete_hospital_link(patient: Patient = Depends(current_patient), db: AsyncSession = Depends(get_db)):
    await hospital_sync.unlink_patient(db, patient)
    return {"linked": False}


# ── programme de vie ─────────────────────────────────────────────────────────
async def medications_block(db: AsyncSession, patient: Patient, source: Optional[str]) -> dict[str, Any]:
    now = patient_now(patient).replace(tzinfo=None)
    items = (await db.execute(select(PrescriptionItem).join(Prescription, Prescription.id == PrescriptionItem.prescription_id)
                              .where(Prescription.patient_id == patient.id, Prescription.is_current.is_(True)))).scalars().all()
    nxt = (await db.execute(
        select(PrescriptionItem.medication_name, MedicationDose.scheduled_date, MedicationDose.scheduled_time)
        .join(PrescriptionItem, PrescriptionItem.id == MedicationDose.prescription_item_id)
        .where(MedicationDose.patient_id == patient.id, MedicationDose.status.in_([DoseStatus.SCHEDULED, DoseStatus.DUE, DoseStatus.REMINDING]), MedicationDose.scheduled_date >= now.date())
        .order_by(MedicationDose.scheduled_date, MedicationDose.scheduled_time).limit(40))).all()
    upcoming = next((r for r in nxt if datetime.combine(r[1], r[2]) >= now), None)
    return {"count": len(items), "next_dose": {"name": upcoming[0], "time": datetime.combine(upcoming[1], upcoming[2]).isoformat()} if upcoming else None,
            "source": source or "ordonnance de votre médecin", "items": [{"name": i.medication_name, "dose": i.dosage, "times": i.scheduled_times or []} for i in items]}


@router.get("/care-program")
async def get_care_program(patient: Patient = Depends(current_patient), db: AsyncSession = Depends(get_db)):
    program = await care_plan_agent.current_program(db, patient.id)
    if not program:
        raise HTTPException(status_code=404, detail="Aucun programme généré : liez d'abord votre dossier hospitalier.")
    adh = await care_plan_agent.adherence(db, patient.id)
    return care_plan_agent.program_out(program, await medications_block(db, patient, program.source), adh)


class ValidateRequest(BaseModel):
    decision: Literal["apply"] = "apply"


@router.post("/care-program/{program_id}/validate")
async def validate_care_program(program_id: str, body: ValidateRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Validation humaine : un médecin applique le brouillon (les plans d'alimentation et d'activité deviennent actifs)."""
    if current_user.role not in (UserRole.DOCTOR, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Seul un médecin peut valider le programme.")
    import uuid as _uuid

    try:
        pid = _uuid.UUID(program_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Programme introuvable")
    program = (await db.execute(select(CareProgram).where(CareProgram.id == pid))).scalar_one_or_none()
    if not program or not program.is_current:
        raise HTTPException(status_code=404, detail="Programme introuvable ou remplacé")
    await care_plan_agent.apply_program(db, program, validated_by=current_user.email, auto=False)
    return {"id": str(program.id), "status": program.status, "validated_by": program.validated_by}


# ── journal de l'agent ───────────────────────────────────────────────────────
@router.get("/agent/runs")
async def agent_runs(limit: int = 10, patient: Patient = Depends(current_patient), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AgentRun).where(AgentRun.patient_id == patient.id).order_by(AgentRun.started_at.desc()).limit(max(1, min(50, limit))))).scalars().all()
    return [care_plan_agent.run_out(r) for r in rows]


@router.post("/agent/run")
async def agent_run_now(patient: Patient = Depends(current_patient), db: AsyncSession = Depends(get_db)):
    """Suivi d'observance à la demande (sans nouvelle synchronisation)."""
    if not await hospital_sync.subscription_active(db, patient.id):
        raise HTTPException(status_code=402, detail="Un abonnement actif est nécessaire.")
    return care_plan_agent.run_out(await care_plan_agent.run(db, patient, None, trigger="adherence"))


# ── abonnement ───────────────────────────────────────────────────────────────
class ActivateRequest(BaseModel):
    plan: Literal["monthly", "quarterly"] = "monthly"


@router.get("/subscription")
async def get_subscription(patient: Patient = Depends(current_patient), db: AsyncSession = Depends(get_db)):
    return hospital_sync.subscription_out(await hospital_sync.current_subscription(db, patient.id))


@router.post("/subscription/activate")
async def activate_subscription(body: ActivateRequest, patient: Patient = Depends(current_patient), db: AsyncSession = Depends(get_db)):
    """Activation de démonstration — aucun paiement réel."""
    try:
        return hospital_sync.subscription_out(await hospital_sync.activate_subscription(db, patient.id, body.plan))
    except hospital_sync.LinkError as exc:
        _raise(exc)
