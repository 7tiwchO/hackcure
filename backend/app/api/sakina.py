import logging
from time import monotonic

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.patient import Patient
from app.services import sakina_context
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

router = APIRouter(prefix="/api", tags=["Sakina psychological support"])
logger = logging.getLogger(__name__)


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
            emergency_numbers=numbers,
        )
    if not rate_limit_allows(str(current_user.id)):
        raise HTTPException(status_code=429, detail="Please wait a moment before sending another message.")

    # Contexte fondé sur le dossier hospitalier synchronisé (ordonnance, rapport, programme, observance)
    patient = (await db.execute(select(Patient).where(Patient.user_id == current_user.id))).scalar_one_or_none()
    context = {"text": "", "used": {"grounded": False, "label": "", "sources": []}, "facts": {}}
    if patient:
        try:
            context = await sakina_context.build_context(db, patient)
        except Exception:
            logger.exception("sakina context unavailable")
    # Jamais de modification de traitement : refus déterministe, sans passer par le LLM
    med_names = [m.get("name", "") for m in (context["facts"].get("medications") or [])]
    if sakina_context.is_treatment_change_request(latest_message, med_names):
        return SakinaChatResponse(reply=sakina_context.treatment_change_reply(language, context["facts"]), context_used=context["used"], mode="safety")

    started = monotonic()
    try:
        reply = await generate_reply([message.model_dump() for message in payload.history], context["text"])
        if not reply:
            raise ValueError("Anthropic returned an empty message")
        return SakinaChatResponse(reply=reply, context_used=context["used"], mode="llm")
    except Exception as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        logger.warning(
            "sakina upstream failure step=anthropic category=%s status=%s duration_ms=%s",
            type(exc).__name__,
            status,
            int((monotonic() - started) * 1000),
        )
        # Mode sans crédit : réponse de soutien préparée, adaptée au contexte (prochaine prise, observance, conseil du jour)
        try:
            reply = sakina_context.offline_support_reply(latest_message, language, context)
        except Exception:
            reply = _unavailable_reply(language)
        return SakinaChatResponse(reply=reply, fallback=True, context_used=context["used"], mode="offline_support")
