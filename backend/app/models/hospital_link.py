"""Lien avec la plateforme hospitalière (Hospital Copilot), abonnement, programme de vie et exécutions du CarePlanAgent."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy import Uuid as UUID

from app.database import Base


class HospitalLink(Base):
    """Patient de l'application ↔ pseudonyme hospitalier (`PAT-xxxx`). Aucun nom n'est stocké ni échangé."""

    __tablename__ = "hospital_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), unique=True, index=True)
    pseudonym = Column(String, nullable=False, index=True)
    hospital_url = Column(String, nullable=True)
    consent_at = Column(DateTime, nullable=False)          # consentement explicite du patient
    linked_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)         # dernière synchronisation réussie
    last_attempt_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String, nullable=True)       # ok | offline | error
    last_sync_error = Column(Text, nullable=True)
    cached_bundle = Column(JSON, nullable=True)            # dernier Bundle FHIR pseudonymisé (disponible hors ligne)
    cached_digest = Column(String, nullable=True)          # empreinte du contenu clinique : le programme est régénéré s'il change
    rx_digest = Column(String, nullable=True)              # empreinte de l'ordonnance : le calendrier n'est refait que si elle change
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Subscription(Base):
    """Abonnement vendu par l'hôpital à la sortie ; partage de revenus hôpital / équipe HackCure. Aucun paiement réel."""

    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), index=True)
    hospital_name = Column(String, nullable=False)
    plan = Column(String, nullable=False)                  # monthly | quarterly
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String, default=SubscriptionStatus.ACTIVE.value)
    price_tnd = Column(Float, nullable=True)
    hospital_share_pct = Column(Float, nullable=False)
    team_share_pct = Column(Float, nullable=False)
    demo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CareProgram(Base):
    """Programme de vie généré par le CarePlanAgent (alimentation, activité, habitudes). Brouillon tant qu'il n'est pas validé."""

    __tablename__ = "care_programs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), index=True)
    document_source_id = Column(UUID(as_uuid=True), ForeignKey("document_sources.id"), nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
    mode = Column(String, default="rules")                 # llm | rules
    fallback = Column(Boolean, default=False)              # True : LLM indisponible, plan produit par les règles
    status = Column(String, default="draft")               # draft | applied | superseded
    auto_applied = Column(Boolean, default=False)
    validated_by = Column(String, nullable=True)
    validated_at = Column(DateTime, nullable=True)
    source = Column(String, nullable=True)                 # « issu de l'ordonnance du Dr … du … »
    parameters = Column(JSON, nullable=True)               # paramètres cliniques extraits (entrée du plan)
    payload = Column(JSON, nullable=True)                  # nutrition, activity, habits, warnings
    is_current = Column(Boolean, default=True)


class AgentRun(Base):
    """Journal d'une exécution du CarePlanAgent (montré au jury par GET /api/agent/runs)."""

    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    trigger = Column(String, nullable=False)               # link | sync | periodic | adherence | manual
    mode = Column(String, default="rules")
    status = Column(String, default="ok")                  # ok | partial | error
    summary = Column(Text, nullable=True)
    steps = Column(JSON, nullable=True)                    # [{name, status, detail}]
    care_team_note = Column(Text, nullable=True)           # signalement destiné à l'équipe soignante (observance)
    duration_ms = Column(Integer, nullable=True)
