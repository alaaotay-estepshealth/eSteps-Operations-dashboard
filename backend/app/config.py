from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings

# Known-insecure defaults. In production these MUST be overridden via env, else
# the app boots fail-open with a guessable JWT/webhook key. The validator below
# refuses to start a production deployment that still carries any of them.
_INSECURE_JWT_SECRET = "change-this-to-a-random-32-char-string"
_INSECURE_WEBHOOK_SECRET = "n8n-secret-key"
_INSECURE_DATABASE_URL = "postgresql://esteps:esteps123@localhost:5432/esteps_ops"


class Settings(BaseSettings):
    database_url: str = _INSECURE_DATABASE_URL
    jwt_secret: str = _INSECURE_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    ai_daily_budget_usd: float = 10.0
    n8n_webhook_secret: str = _INSECURE_WEBHOOK_SECRET
    n8n_base_url: str = "https://n8n.estepshealth.tech"
    n8n_api_key: str = ""
    environment: str = "development"
    auto_create_db: bool = True
    # Comma-separated allowed CORS origins
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://frontend:5173"
    # Read-only connection to eSteps Leads Automation Supabase project (eu-central-1)
    # Falls back to ops DB when empty
    leads_database_url: str = ""
    strategy_dir: str = ""
    # Optional seed dir for /meets explorer.
    meet_dir: str = ""
    # Optional — enables the AI strategy memo on the Insights view. Missing → memo returns 503.
    gemini_api_key: str = ""
    # Anthropic Claude — direct API for GTM strategy ingest.
    anthropic_api_key: str = ""
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_version: str = "2023-06-01"
    gtm_model: str = "claude-opus-4-7"
    # Separate daily budget for GTM ingest so it can't starve Gemini ops.
    gtm_ai_budget_usd: float = 1.0
    # OpenClaw agent gateway (launch actions / collect data). Missing → OpenClaw endpoints return 503.
    openclaw_base_url: str = ""
    openclaw_hook_token: str = ""

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "Settings":
        """Refuse to boot a production deployment with insecure/default secrets.

        Dev and tests keep their convenient defaults; only `ENVIRONMENT=production`
        triggers these checks so a misconfigured prod deploy fails loudly at
        startup instead of running fail-open.
        """
        if self.environment != "production":
            return self
        problems: List[str] = []
        if self.jwt_secret == _INSECURE_JWT_SECRET or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be a random 32+ character value")
        if self.n8n_webhook_secret == _INSECURE_WEBHOOK_SECRET:
            problems.append("N8N_WEBHOOK_SECRET must be rotated from its default")
        if self.database_url == _INSECURE_DATABASE_URL:
            problems.append("DATABASE_URL must point at the real database")
        if self.auto_create_db:
            problems.append("AUTO_CREATE_DB must be false in production (use Alembic migrations)")
        if problems:
            raise ValueError(
                "Refusing to start in production with insecure config: "
                + "; ".join(problems)
            )
        return self

    class Config:
        env_file = ".env"


settings = Settings()
