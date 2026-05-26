from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://esteps:esteps123@localhost:5432/esteps_ops"
    jwt_secret: str = "change-this-to-a-random-32-char-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    ai_daily_budget_usd: float = 10.0
    n8n_webhook_secret: str = "n8n-secret-key"
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

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
