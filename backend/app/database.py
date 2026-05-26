from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Leads source DB (eSteps Leads Automation Supabase, eu-central-1) ──────────
# Optional second connection — falls back to ops DB when LEADS_DATABASE_URL is unset.
_leads_url = settings.leads_database_url or settings.database_url
_leads_engine = create_engine(_leads_url, pool_pre_ping=True)
LeadsSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_leads_engine)


def get_leads_db():
    db = LeadsSessionLocal()
    try:
        yield db
    finally:
        db.close()
