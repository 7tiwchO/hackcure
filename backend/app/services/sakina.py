import json
import logging
import re
from pathlib import Path
from time import monotonic
from typing import Any

import httpx

from app.config import settings
from app.services.companion import (
    _anthropic,
    _n8n_chat_response,
    _redact_direct_identifiers,
    context_access_token,
    emergency_numbers,
)

_PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "sakina_system.md"
_CONTACTS = Path(__file__).resolve().parents[1] / "safety" / "emergency_contacts.json"
_LOGGER = logging.getLogger(__name__)

_CRISIS_TERMS = (
    # English
    "suicide", "suicidal", "kill myself", "end my life", "want to die", "don't want to live",
    "dont want to live", "self-harm", "self harm", "hurt myself", "harm myself", "abuse",
    "being abused", "someone is hurting me", "i am in danger", "i'm in danger", "in danger", "unsafe right now",
    # French
    "suicide", "suicidaire", "me suicider", "me faire du mal", "me blesser", "envie de mourir",
    "ne veux plus vivre", "violence", "violences", "abus", "je suis en danger", "en danger",
    "quelqu'un me fait du mal", "quelqu’un me fait du mal",
    # Modern Standard Arabic and Tunisian Arabic
    "انتحار", "انتحاري", "أقتل نفسي", "اقتل نفسي", "أؤذي نفسي", "اوذي نفسي", "أضر نفسي",
    "أريد أن أموت", "نريد أن نموت", "لا أريد أن أعيش", "إيذاء النفس", "اعتداء", "عنف",
    "أنا في خطر", "انا في خطر", "نحب نموت", "نقتل روحي", "نأذي روحي", "نضر روحي", "نتعرض للعنف",
)


def is_crisis_message(message: str) -> bool:
    normalized = re.sub(r"\s+", " ", message.casefold()).strip()
    return any(term in normalized for term in _CRISIS_TERMS)


def confirms_safety(message: str) -> bool:
    normalized = re.sub(r"\s+", " ", message.casefold()).strip()
    confirmations = (
        "i am safe now", "i'm safe now", "im safe now", "i am safe", "i'm safe",
        "je suis en sécurité", "je suis en securite", "je suis en sûreté", "je suis en surete",
        "أنا بأمان", "انا بأمان", "أنا في أمان", "انا في امان", "أنا بخير الآن", "انا بخير توا",
    )
    return any(term in normalized for term in confirmations)


def detect_language(message: str, preferred_language: str | None = None) -> str:
    if re.search(r"[\u0600-\u06ff]", message):
        return "ar"
    if re.search(r"\b(je|j'ai|j’ai|moi|avec|suis|une|mon|ma|mes|pas|est|ça|ca|vous|bonjour|merci)\b", message.casefold()):
        return "fr"
    if re.search(r"\b(i|i'm|im|my|me|you|am|feel|hello|help|the|and|not|is)\b", message.casefold()):
        return "en"
    preferred = (preferred_language or "en").split("-")[0].lower()
    return preferred if preferred in {"ar", "fr", "en"} else "en"


def get_emergency_numbers(country: str | None = None) -> list[dict[str, str]]:
    configured = json.loads(_CONTACTS.read_text(encoding="utf-8"))
    return configured.get((country or settings.CHAT_DEFAULT_COUNTRY).upper(), {}).get("numbers", [])


def localized_crisis_reply(language: str, has_numbers: bool) -> str:
    if language == "fr":
        contacts = " Les numéros d’urgence sont affichés juste ici." if has_numbers else " Contactez les services d’urgence de votre région."
        return "Je suis vraiment désolé que vous traversiez cela. Vous méritez du soutien maintenant. Si vous êtes en danger immédiat ou risquez de vous faire du mal, appelez les urgences et, si vous le pouvez, rapprochez-vous d’une personne de confiance.{contacts}".format(contacts=contacts)
    if language == "ar":
        contacts = " أرقام الطوارئ ظاهرة هنا." if has_numbers else " اتصل بخدمات الطوارئ المحلية."
        return "آسف لأنك تمرّ بهذا. أنت تستحق الدعم الآن. إذا كنت في خطر مباشر أو قد تؤذي نفسك، اتصل بالطوارئ وحاول الوصول إلى شخص تثق به ليبقى معك.{contacts}".format(contacts=contacts)
    contacts = " Emergency numbers are shown here." if has_numbers else " Contact your local emergency services."
    return "I’m sorry you’re going through this. You deserve support right now. If you’re in immediate danger or might hurt yourself, contact emergency services and, if you can, reach out to someone you trust nearby.{contacts}".format(contacts=contacts)


async def generate_reply(
    history: list[dict[str, str]],
    patient: Any | None = None,
    patient_id: str | None = None,
    session_id: str | None = None,
    language: str = "en",
) -> tuple[str, bool, str | None, str | None]:
    prompt = _PROMPT.read_text(encoding="utf-8")
    safe_history = [
        {"role": message["role"], "content": _redact_direct_identifiers(message["content"], patient)}
        for message in history
    ]
    started = monotonic()

    if settings.CHAT_N8N_CHAT_WEBHOOK_URL and settings.CHAT_N8N_SHARED_SECRET:
        if not patient_id or not session_id:
            return "", True, "CHAT_PATIENT_CONTEXT_UNAVAILABLE", None
        try:
            async with httpx.AsyncClient(timeout=settings.CHAT_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    settings.CHAT_N8N_CHAT_WEBHOOK_URL,
                    headers={"X-HackCure-Secret": settings.CHAT_N8N_SHARED_SECRET},
                    json={
                        "patient_id": patient_id,
                        "session_id": session_id,
                        "context_token": context_access_token(patient_id, session_id),
                        "message": safe_history[-1]["content"],
                        "language": language,
                        "history": safe_history[:-1],
                        "rolling_summary": "",
                        "system_prompt": prompt,
                        "emergency_numbers": emergency_numbers(),
                    },
                )
            response.raise_for_status()
            upstream = _n8n_chat_response(response.json())
            return upstream.reply, upstream.fallback, upstream.error_code, upstream.triage_label
        except Exception as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            _LOGGER.warning(
                "sakina upstream failure step=n8n category=%s status=%s duration_ms=%s",
                type(exc).__name__,
                status,
                int((monotonic() - started) * 1000),
            )
            if isinstance(exc, httpx.TimeoutException):
                code = "CHAT_N8N_TIMEOUT"
            elif status in {401, 403}:
                code = "CHAT_N8N_AUTH_FAILED"
            elif status == 404:
                code = "CHAT_N8N_WEBHOOK_INACTIVE"
            elif status:
                code = "CHAT_N8N_WORKFLOW_FAILED"
            elif isinstance(exc, (ValueError, TypeError)):
                code = "CHAT_N8N_INVALID_RESPONSE"
            else:
                code = "CHAT_N8N_UNAVAILABLE"
            return "", True, code, None

    try:
        reply = await _anthropic(settings.SAKINA_MODEL, prompt, safe_history, settings.CHAT_MAX_TOKENS)
        return reply, False, None, None
    except Exception as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        _LOGGER.warning(
            "sakina upstream failure step=anthropic category=%s status=%s duration_ms=%s",
            type(exc).__name__,
            status,
            int((monotonic() - started) * 1000),
        )
        if not settings.ANTHROPIC_API_KEY:
            code = "CHAT_PROVIDER_NOT_CONFIGURED"
        elif isinstance(exc, httpx.TimeoutException):
            code = "CHAT_PROVIDER_TIMEOUT"
        elif status == 401 or status == 403:
            code = "CHAT_PROVIDER_AUTH_FAILED"
        elif status == 404:
            code = "CHAT_MODEL_NOT_FOUND"
        elif status == 429:
            code = "CHAT_PROVIDER_RATE_LIMITED"
        else:
            code = "CHAT_PROVIDER_UNAVAILABLE"
        return "", True, code, None
