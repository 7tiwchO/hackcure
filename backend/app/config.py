from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "HackCure API"
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "sqlite+aiosqlite:///./hackcure.db"
    SECRET_KEY: str = "hackcure-super-secure-production-ready-jwt-key-32chars-min"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    CORS_ORIGINS: List[str] = ["*"]
    AUTOMATION_API_KEY: str = "hackcure-automation-dev-key-2026"
    ANTHROPIC_API_KEY: str = ""
    CHAT_MODEL: str = "claude-sonnet-5"
    SAKINA_MODEL: str = "claude-sonnet-4-6"
    TRIAGE_MODEL: str = "claude-haiku-4-5-20251001"
    CHAT_MAX_TOKENS: int = 700
    CHAT_TIMEOUT_SECONDS: float = 45.0
    CHAT_RATE_LIMIT_PER_MINUTE: int = 12
    CHAT_N8N_WEBHOOK_BASE_URL: str = ""
    CHAT_N8N_CHAT_WEBHOOK_URL: str = ""
    CHAT_N8N_SHARED_SECRET: str = ""
    CHAT_DIAGNOSTIC_TOKEN: str = ""
    CHAT_DEFAULT_COUNTRY: str = "TN"
    PATIENT_TIMEZONE: str = "Africa/Tunis"
    # Lien avec la plateforme hospitaliere Hospital Copilot (API FHIR en lecture)
    HOSPITAL_COPILOT_URL: str = "http://localhost:8000"
    HOSPITAL_COPILOT_SERVICE_TOKEN: str = ""      # = PLATFORM_SERVICE_TOKEN de l'hopital
    HOSPITAL_COPILOT_TIMEOUT_SECONDS: float = 8.0
    HOSPITAL_COPILOT_RETRIES: int = 3
    HOSPITAL_COPILOT_VERIFY_TLS: bool = True      # False pour un certificat auto-signe de demonstration
    HOSPITAL_SYNC_INTERVAL_MINUTES: float = 0     # 0 = pas de synchronisation periodique
    HOSPITAL_NAME: str = "Clinique HackCure"
    # CarePlanAgent
    CARE_AGENT_USE_LLM: bool = True               # sans cle ou si l'appel echoue : plan par regles (mode de secours)
    DEMO_AUTO_APPLY: bool = False                 # True : programme applique sans validation medicale (demonstration)
    # Abonnement : part de l'hopital en % (le reste revient a l'equipe HackCure)
    SUBSCRIPTION_HOSPITAL_SHARE_PCT: float = 60.0

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
