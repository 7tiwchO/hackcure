import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.dependencies import get_current_user
from app.models.patient import Patient
from app.models.user import User, UserRole
from app.schemas.sakina import SakinaChatRequest, SakinaChatResponse
from app.services.companion import rate_limit_allows
from app.services.sakina import (
    detect_language,
    confirms_safety,
    generate_reply,
    get_emergency_numbers,
    is_crisis_message,
    localized_crisis_reply,
)
from app.services.companion import safety_reply, triage

router = APIRouter(prefix="/api", tags=["Sakina psychological support"])


def _unavailable_reply(language: str) -> str:
    if language == "fr":
        return "Je suis désolée, je rencontre un problème de connexion. Votre conversation reste sur cet écran ; vous pouvez réessayer dans un instant."
    if language == "ar":
        return "عذراً، أواجه مشكلة في الاتصال. محادثتك باقية على هذه الشاشة؛ يمكنك إعادة المحاولة بعد قليل."
    return "I’m sorry, I’m having a connection problem. Your conversation stays on this screen; you can try again in a moment."


@router.post("/chat", response_model=SakinaChatResponse)
async def chat_with_sakina(
    payload: SakinaChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a reply from the supplied in-memory history without persisting it."""
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Patient account required")
    patient_result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
    patient = patient_result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
    latest_message = payload.history[-1].content
    language = detect_language(latest_message, current_user.language)
    prior_crisis = any(
        message.role == "user" and is_crisis_message(message.content)
        for message in payload.history[:-1]
    )
    if is_crisis_message(latest_message) or (prior_crisis and not confirms_safety(latest_message)):
        numbers = get_emergency_numbers()
        return SakinaChatResponse(
            reply=localized_crisis_reply(language, bool(numbers)),
            crisis=True,
            triage_label="self_harm_or_suicide_risk",
            emergency_numbers=numbers,
        )
    if not rate_limit_allows(str(current_user.id)):
        raise HTTPException(status_code=429, detail="Please wait a moment before sending another message.")

    uses_n8n = bool(settings.CHAT_N8N_CHAT_WEBHOOK_URL and settings.CHAT_N8N_SHARED_SECRET)
    triage_label = None
    if not uses_n8n:
        triage_label, _ = await triage(latest_message, patient)
        if triage_label in {"self_harm_or_suicide_risk", "medical_emergency", "medication_change_request"}:
            return SakinaChatResponse(
                reply=safety_reply(triage_label, language),
                crisis=triage_label in {"self_harm_or_suicide_risk", "medical_emergency"},
                triage_label=triage_label,
                emergency_numbers=get_emergency_numbers() if triage_label != "medication_change_request" else [],
            )

    reply, fallback, error_code, upstream_triage_label = await generate_reply(
        [message.model_dump() for message in payload.history],
        patient=patient,
        patient_id=str(patient.id),
        session_id=str(current_user.id),
        language=language,
    )
    triage_label = upstream_triage_label or triage_label
    if fallback or not reply:
        return SakinaChatResponse(
            reply=_unavailable_reply(language),
            fallback=True,
            error_code=error_code or "CHAT_UPSTREAM_UNAVAILABLE",
            triage_label=triage_label,
        )
    return SakinaChatResponse(reply=reply, triage_label=triage_label)
