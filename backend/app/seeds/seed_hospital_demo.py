"""
Seed de démonstration du lien hospitalier.

    python -m app.seeds.seed_hospital_demo            # crée le compte, l'abonnement et le lien (sans réseau)
    python -m app.seeds.seed_hospital_demo --sync     # … puis synchronise avec Hospital Copilot s'il répond

Crée la patiente de l'application liée au séjour `PAT-0004` de la plateforme hospitalière (chambre 104) :
  compte  zohra@example.com / Test123!@#   — abonnement de démonstration actif — lien avec consentement.
Idempotent. Le lien est créé directement (consentement de démonstration) : la vérification pseudonyme + date de
naissance est celle de l'écran « Lier mon dossier hospitalier » ; ici elle est refaite si `--sync` est demandé.
"""
import asyncio
import sys
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select

import app.models  # noqa: F401  (enregistre tous les modèles)
from app.config import settings
from app.database import AsyncSessionLocal, Base, engine
from app.models.hospital_link import HospitalLink, Subscription, SubscriptionStatus
from app.models.patient import Gender, Patient
from app.models.user import User, UserRole
from app.utils.security import get_password_hash

DEMO_EMAIL = "zohra@example.com"
DEMO_PASSWORD = "Test123!@#"
DEMO_PSEUDONYM = "PAT-0004"


def demo_birth_date() -> date:
    """Date de naissance de la patiente de démonstration dans Hospital Copilot (75 ans, née un 14 juillet)."""
    return date(date.today().year - 75, 7, 14)


async def seed(sync: bool = False) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == DEMO_EMAIL))).scalar_one_or_none()
        if not user:
            user = User(id=uuid.uuid4(), email=DEMO_EMAIL, phone="+216 98 000 104", password_hash=get_password_hash(DEMO_PASSWORD), role=UserRole.PATIENT, is_active=True, is_verified=True, language="fr")
            db.add(user)
            await db.flush()
        patient = (await db.execute(select(Patient).where(Patient.user_id == user.id))).scalar_one_or_none()
        if not patient:
            patient = Patient(id=uuid.uuid4(), user_id=user.id, first_name="Zohra", last_name="C.", date_of_birth=demo_birth_date(), gender=Gender.FEMALE, blood_type="AB+",
                              allergies=["AINS", "aspirine"], address="Tunis")
            db.add(patient)
            await db.flush()
        elif patient.date_of_birth != demo_birth_date():
            patient.date_of_birth = demo_birth_date()
        sub = (await db.execute(select(Subscription).where(Subscription.patient_id == patient.id))).scalars().first()
        share = float(settings.SUBSCRIPTION_HOSPITAL_SHARE_PCT)
        if not sub:
            db.add(Subscription(patient_id=patient.id, hospital_name=settings.HOSPITAL_NAME, plan="quarterly", start_date=date.today(), end_date=date.today() + timedelta(days=90),
                                status=SubscriptionStatus.ACTIVE.value, price_tnd=75.0, hospital_share_pct=share, team_share_pct=round(100 - share, 2), demo=True))
        elif sub.end_date < date.today() + timedelta(days=7):
            sub.end_date, sub.status = date.today() + timedelta(days=90), SubscriptionStatus.ACTIVE.value
        link = (await db.execute(select(HospitalLink).where(HospitalLink.patient_id == patient.id))).scalar_one_or_none()
        if not link:
            db.add(HospitalLink(patient_id=patient.id, pseudonym=DEMO_PSEUDONYM, consent_at=datetime.utcnow(), linked_at=datetime.utcnow(), hospital_url=settings.HOSPITAL_COPILOT_URL))
        elif link.revoked_at is not None:
            link.revoked_at, link.consent_at = None, datetime.utcnow()
        await db.commit()
        print(f"Patiente de démonstration : {DEMO_EMAIL} / {DEMO_PASSWORD} — liée à {DEMO_PSEUDONYM} — abonnement actif")
        if sync:
            from app.services import hospital_sync

            try:
                status = await hospital_sync.sync_patient(db, patient, trigger="seed")
                print(f"Synchronisation : {status['last_sync_status']} — {len(status['documents'])} document(s) — agent : {(status.get('last_agent_run') or {}).get('summary')}")
            except Exception as exc:  # hôpital arrêté : le lien reste prêt, la synchronisation se fera depuis l'application
                print(f"Synchronisation non faite ({type(exc).__name__}: {exc}). Lancez Hospital Copilot puis « Synchroniser maintenant ».")


if __name__ == "__main__":
    asyncio.run(seed(sync="--sync" in sys.argv))
