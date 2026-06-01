from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.config import settings
from app.routers import admin, auth, webhooks
from app.routers import systems as systems_router
from app.routers import n8n_proxy
from app.routers import email_logs, bookings, opportunities, tickets, gtm
from app.routers import lead_actions
from app.routers import insights
from app.routers import followups, contacts, briefing, openclaw

if settings.environment == "development" and settings.auto_create_db:
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="eSteps Ops Dashboard API",
    description="Multi-system automation operations dashboard (ES-OPS-09)",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(webhooks.router)
app.include_router(systems_router.router)
app.include_router(n8n_proxy.router)
app.include_router(email_logs.router)
app.include_router(bookings.router)
app.include_router(opportunities.router)
app.include_router(tickets.router)
app.include_router(gtm.router)
app.include_router(lead_actions.router)
app.include_router(insights.router)
app.include_router(followups.router)
app.include_router(contacts.router)
app.include_router(briefing.router)
app.include_router(openclaw.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "eSteps Ops API"}
