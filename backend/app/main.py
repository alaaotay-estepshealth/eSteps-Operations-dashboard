from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.database import Base, engine
from app.config import settings
from app.rate_limit import limiter
from app.routers import admin, auth, webhooks
from app.routers import systems as systems_router
from app.routers import n8n_proxy
from app.routers import email_logs, bookings, opportunities, tickets, gtm, meets, meetings
from app.routers import suggestions
from app.routers import lead_actions
from app.routers import insights
from app.routers import followups, contacts, briefing, openclaw, users
from app.routers import gtm_plan

if settings.environment == "development" and settings.auto_create_db:
    Base.metadata.create_all(bind=engine)

_is_prod = settings.environment == "production"

app = FastAPI(
    title="eSteps Ops Dashboard API",
    description="Multi-system automation operations dashboard (ES-OPS-09)",
    version="2.0.0",
    # Hide interactive API docs in production (they enumerate every endpoint).
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

# Rate limiting (active only when ENVIRONMENT=production — see app/rate_limit.py).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-N8N-Signature"],
)

if _is_prod:
    # Never leak tracebacks/internal details to clients in production.
    @app.exception_handler(Exception)
    async def _generic_error_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

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
app.include_router(meets.router)
app.include_router(meetings.router)
app.include_router(suggestions.router)
app.include_router(lead_actions.router)
app.include_router(insights.router)
app.include_router(followups.router)
app.include_router(contacts.router)
app.include_router(briefing.router)
app.include_router(openclaw.router)
app.include_router(users.router)
app.include_router(gtm_plan.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "eSteps Ops API"}
