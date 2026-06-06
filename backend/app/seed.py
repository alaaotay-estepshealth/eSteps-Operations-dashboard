"""
Seed the database with realistic demo data matching the eSteps lead generation system.
Run: python -m app.seed
"""
import random
import uuid
from datetime import datetime, timedelta

from faker import Faker
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.database import SessionLocal, engine
from app.models import (
    Booking,
    Ticket,
    WorkflowExecution,
    AIRequest,
    AuditLog,
    User,
)
from app.models.system import System
from app.database import Base

fake = Faker()

RESEARCH_INTERESTS = [
    "gait_analysis", "parkinsons", "rehabilitation",
    "fall_prevention", "aging", "neurology", "orthopedics", "general",
]
STAGES = ["new", "introduced", "pitching", "call_requested", "engaged", "meeting_booked", "cold", "dead"]
INSTITUTIONS = [
    "University of Florida", "Mayo Clinic", "Stanford University",
    "Johns Hopkins", "MIT", "Harvard Medical School", "UCLA",
    "University of Michigan", "Duke University", "NYU Langone",
]
LEAD_SOURCES = ["csv_import", "linkedin", "manual", "conference", "referral"]

SYSTEMS_DATA = [
    {
        "slug": "esteps-leads",
        "name": "eSteps Leads",
        "description": "Academic researcher outreach and partnership pipeline",
        "webhook_secret": "esteps-leads-secret-change-me",
        "n8n_project_id": None,
        "workflows": [
            ("est-2", "EST-2: Outreach Engine"),
            ("est-3", "EST-3: Reply Handler"),
            ("est-5", "EST-5: Booking Sync"),
        ],
    },
    {
        "slug": "wam-agency",
        "name": "WAM Agency",
        "description": "B2B agency lead generation and nurture automation",
        "webhook_secret": "wam-agency-secret-change-me",
        "n8n_project_id": None,
        "workflows": [
            ("wam-enrich", "WAM: Lead Enrichment"),
            ("wam-outreach", "WAM: Cold Outreach"),
        ],
    },
    {
        "slug": "ai-chatbot",
        "name": "AI Chatbot",
        "description": "Customer-facing AI assistant and ticket routing",
        "webhook_secret": "ai-chatbot-secret-change-me",
        "n8n_project_id": None,
        "workflows": [
            ("chat-router", "Chat: Intent Router"),
            ("chat-escalate", "Chat: Human Escalation"),
        ],
    },
    {
        "slug": "solar-leads",
        "name": "Solar Leads",
        "description": "Solar energy lead capture and qualification pipeline",
        "webhook_secret": "solar-leads-secret-change-me",
        "n8n_project_id": None,
        "workflows": [
            ("solar-qualify", "Solar: Lead Qualification"),
        ],
    },
    {
        "slug": "ai-influencer",
        "name": "AI Influencer",
        "description": "AI-generated content and influencer outreach automation",
        "webhook_secret": "ai-influencer-secret-change-me",
        "n8n_project_id": None,
        "workflows": [
            ("inf-generate", "Influencer: Content Generation"),
            ("inf-publish", "Influencer: Publish & Track"),
        ],
    },
]

AI_TYPES = ["lead_classify", "email_summarize", "priority_score", "draft_reply", "log_summarize"]
LOG_SOURCES = ["fastapi", "n8n", "ai_service", "est-2", "est-3", "est-5"]
EMAIL_PROVIDERS = ["gmail", "sendgrid", "outlook"]
OPPORTUNITY_STAGES = ["meeting_booked", "call_held", "proposal_sent", "pilot_active", "closed_won", "closed_lost"]
PARTNERSHIP_TIERS = ["pilot", "research_partner", "strategic_partner"]
BOOKING_STATUSES = ["scheduled", "completed", "canceled", "no_show"]
SIM_ERRORS = [
    ("Gmail rate limit reached", "rate_limit"),
    ("Supabase timeout", "timeout"),
    ("OpenAI API error: 429", "api_error"),
    ("Webhook delivery failed", "delivery_error"),
]


def seed_systems(db: Session) -> dict:
    """Seed systems table. Returns {slug: System} mapping."""
    existing = {s.slug: s for s in db.query(System).all()}
    created = 0
    for data in SYSTEMS_DATA:
        if data["slug"] not in existing:
            system = System(
                slug=data["slug"],
                name=data["name"],
                description=data["description"],
                webhook_secret=data["webhook_secret"],
                n8n_project_id=data.get("n8n_project_id"),
            )
            db.add(system)
            existing[data["slug"]] = system
            created += 1
    db.commit()
    # Refresh to get IDs
    all_systems = {s.slug: s for s in db.query(System).all()}
    print(f"  ✓ {created} systems created ({len(all_systems)} total)")
    return all_systems


TEST_USERS = [
    # username, email, password, role
    ("admin",    "admin@estepshealth.com",    "admin123",    "admin"),
    ("operator", "operator@estepshealth.com", "operator123", "operator"),
    ("viewer",   "viewer@estepshealth.com",   "viewer123",   "readonly"),
]


def seed_users(db: Session):
    """Upsert TEST_USERS — creates missing rows, normalizes role + password
    on existing rows so the documented credentials always work."""
    created = updated = 0
    for username, email, password, role in TEST_USERS:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            db.add(User(
                username=username,
                email=email,
                hashed_password=hash_password(password),
                role=role,
                is_active=True,
            ))
            created += 1
        else:
            user.email = email
            user.hashed_password = hash_password(password)
            user.role = role
            user.is_active = True
            updated += 1
    db.commit()
    print(f"  ✓ Users: {created} created, {updated} normalized")


def seed_workflow_executions(db: Session, systems: dict, count: int = 500):
    if db.query(WorkflowExecution).count() > 0:
        return
    executions = []
    all_system_workflows = []
    for sdata in SYSTEMS_DATA:
        sys = systems.get(sdata["slug"])
        if sys:
            for wf_id, wf_name in sdata["workflows"]:
                all_system_workflows.append((sys.id, wf_id, wf_name))

    for _ in range(count):
        system_id, wf_id, wf_name = random.choice(all_system_workflows)
        started = datetime.utcnow() - timedelta(
            days=random.randint(0, 14),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        success = random.random() < 0.93
        duration = random.uniform(0.8, 8.0)
        err_msg, err_type = (None, None)
        if not success:
            err_msg, err_type = random.choice(SIM_ERRORS)
        executions.append(WorkflowExecution(
            system_id=system_id,
            workflow_id=wf_id,
            workflow_name=wf_name,
            execution_id=f"exec_{uuid.uuid4().hex[:12]}",
            status="success" if success else "failed",
            started_at=started,
            finished_at=started + timedelta(seconds=duration),
            duration_seconds=round(duration, 2),
            retry_count=0 if success else random.randint(0, 3),
            error_message=err_msg,
            error_type=err_type,
            correlation_id=f"corr_{uuid.uuid4().hex[:8]}",
        ))
    db.add_all(executions)
    db.commit()
    print(f"  ✓ Created {count} workflow executions")


def seed_ai_requests(db: Session, systems: dict, count: int = 350):
    if db.query(AIRequest).count() > 0:
        return
    system_ids = [s.id for s in systems.values()]
    requests = []
    for _ in range(count):
        conf = random.uniform(0.60, 0.99)
        used_fallback = random.random() < 0.05
        pending = conf < 0.85 and random.random() < 0.3
        tokens = random.randint(150, 800)
        cost = round(tokens * 0.000022, 6)
        requests.append(AIRequest(
            system_id=random.choice(system_ids),
            request_type=random.choice(AI_TYPES),
            workflow_source=random.choice(LOG_SOURCES),
            entity_type=random.choice(["lead", "ticket"]),
            provider=random.choice(["openai", "openai", "gemini"]),
            model=random.choice(["gpt-4o", "gpt-4o-mini", "gemini-1.5-flash"]),
            tokens_used=tokens,
            cost_usd=cost,
            latency_ms=random.randint(400, 2200),
            input_preview=fake.sentence(nb_words=15)[:200],
            ai_output={"category": random.choice(["support", "partnership", "billing"]),
                       "confidence": round(conf, 3), "reason": fake.sentence()},
            confidence_score=round(conf, 3),
            used_fallback=used_fallback,
            fallback_reason="rate_limited" if used_fallback else None,
            human_verified=random.random() < 0.12,
            human_override=random.random() < 0.05,
            status="pending_review" if pending else "completed",
            created_at=datetime.utcnow() - timedelta(days=random.randint(0, 7),
                                                       hours=random.randint(0, 23)),
        ))
    db.add_all(requests)
    db.commit()
    print(f"  ✓ Created {count} AI requests")


def seed_audit_logs(db: Session, systems: dict, count: int = 600):
    if db.query(AuditLog).count() > 0:
        return
    system_ids = [s.id for s in systems.values()]
    levels_weights = [("INFO", 70), ("WARNING", 20), ("ERROR", 8), ("CRITICAL", 2)]
    levels = [l for l, w in levels_weights for _ in range(w)]
    messages = {
        "INFO": ["Workflow completed successfully", "Lead processed", "Email sent",
                 "Webhook received", "AI classification complete", "Booking synced"],
        "WARNING": ["AI confidence below threshold", "Retry attempt", "Rate limit approaching",
                    "Slow query detected", "OOO detected"],
        "ERROR": ["Gmail rate limit reached", "AI API timeout", "Webhook delivery failed",
                  "Database connection reset", "n8n execution failed"],
        "CRITICAL": ["AI budget exceeded", "Database unreachable", "Auth service down"],
    }
    logs = []
    for _ in range(count):
        level = random.choice(levels)
        logs.append(AuditLog(
            system_id=random.choice(system_ids),
            level=level,
            source=random.choice(LOG_SOURCES),
            message=random.choice(messages[level]),
            correlation_id=f"corr_{uuid.uuid4().hex[:8]}",
            duration_ms=random.randint(5, 1500) if level == "INFO" else None,
            created_at=datetime.utcnow() - timedelta(hours=random.randint(0, 72)),
        ))
    db.add_all(logs)
    db.commit()
    print(f"  ✓ Created {count} audit logs")


def seed_tickets(db: Session, count: int = 80):
    if db.query(Ticket).count() > 0:
        return
    tickets = []
    for _ in range(count):
        conf = random.uniform(0.65, 0.98)
        tickets.append(Ticket(
            source=random.choice(["email", "chat", "form", "whatsapp"]),
            subject=fake.sentence(nb_words=6),
            body_preview=fake.paragraph(nb_sentences=3)[:500],
            ai_category=random.choice(["support", "partnership", "billing", "technical"]),
            ai_priority_score=random.randint(1, 5),
            ai_confidence=round(conf, 3),
            assigned_to=random.choice(["nidhal@estepshealth.com", "ops@estepshealth.com"]),
            status=random.choice(["open", "open", "in_progress", "resolved"]),
            response_time_min=round(random.uniform(10, 240), 1),
            human_verified=random.random() < 0.3,
            gdpr_consent=True,
        ))
    db.add_all(tickets)
    db.commit()
    print(f"  ✓ Created {count} tickets")


def run():
    print("\n🌱 Seeding eSteps Ops database...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_users(db)
        systems = seed_systems(db)
        # leads/email_logs/opportunities now live in the LEADS Supabase project
        # (eu-central-1, LEADS_DATABASE_URL). Bookings join via a soft UUID
        # reference, so don't fabricate them here without a real lead UUID.
        seed_workflow_executions(db, systems)
        seed_ai_requests(db, systems)
        seed_audit_logs(db, systems)
        seed_tickets(db)
        print("\n✅ Seed complete.\n")
        print("  Test accounts:")
        for username, _email, password, role in TEST_USERS:
            print(f"    • {username:<8} / {password:<12} (role: {role})")
        print()
        print("  Systems seeded:")
        for s in systems.values():
            print(f"    • {s.slug} — POST /webhooks/{s.slug}")
        print()
    finally:
        db.close()


if __name__ == "__main__":
    run()
