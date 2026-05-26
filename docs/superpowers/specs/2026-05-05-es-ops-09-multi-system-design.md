# ES-OPS-09 Multi-System Backend + Frontend Design

**Date**: 2026-05-05  
**Status**: Approved — proceeding to implementation

---

## 1. Problem

Dashboard is single-system (eSteps Leads only). Five automation systems exist in n8n and need unified monitoring: eSteps Leads, WAM Agency, AI Chatbot, Solar Leads, AI Influencer. Each system lives in its own Supabase project.

---

## 2. Architecture: Single Ops DB + Webhook-Push

**Chosen: Option A — Central Ops Supabase, n8n pushes execution data.**

Dashboard never queries per-system Supabase projects directly. n8n reads each system's data, runs automation, then pushes execution results to the central Ops DB via webhooks.

```
[eSteps Supabase]  ─┐
[WAM Supabase]     ─┤  n8n workflows → POST /webhooks/{system_slug}  →  [Ops Supabase]
[Solar Supabase]   ─┤                                                          │
[AI Chat Supabase] ─┘                                                   FastAPI Dashboard
```

**Why**: 5+ DB connections would explode connection pools and credential surface. Dashboard is a monitoring layer — it receives pushed state, not a data access layer.

---

## 3. Data Model

### 3.1 New: `systems` table (registry anchor)

```sql
systems
  id          UUID PK default gen_random_uuid()
  slug        VARCHAR(50) UNIQUE NOT NULL   -- "esteps-leads", "wam-agency"
  name        VARCHAR(255) NOT NULL
  description TEXT
  webhook_secret  VARCHAR(255) NOT NULL     -- per-system HMAC secret
  n8n_project_id  VARCHAR(100)             -- for API proxy
  is_active   BOOLEAN DEFAULT true
  created_at  TIMESTAMP
  updated_at  TIMESTAMP
```

### 3.2 Modified: add `system_id` to shared tables

Additive nullable FK approach:

```sql
-- workflow_executions, ai_requests, audit_logs:
ALTER TABLE <table> ADD COLUMN system_id UUID REFERENCES systems(id);
```

Migration order:
1. Create `systems` table
2. Add nullable `system_id` columns
3. Seed `esteps-leads` system row
4. Backfill existing rows → `esteps-leads` system_id
5. Enforce `NOT NULL` constraint

**Untouched tables**: `leads`, `email_logs`, `bookings`, `opportunities`, `tickets`, `users`  
**All existing endpoints**: unchanged, backward-compatible.

---

## 4. Backend Architecture

### 4.1 SQLAlchemy: Keep sync

Existing `create_engine` / `SessionLocal` / `get_db` pattern unchanged. No async migration.

### 4.2 Service Layer (DI + SystemService)

Rule: simple single-table queries → router. Aggregations / cross-system queries → `SystemService`.

```python
# app/services/system_service.py
class SystemService:
    def __init__(self, db: Session): ...
    def get_by_slug(self, slug: str) -> System: ...
    def get_cross_system_overview(self) -> dict: ...
    def get_system_stats(self, system_id: UUID) -> dict: ...
```

FastAPI dependency for system resolution:

```python
# app/dependencies.py
def get_system(system_slug: str, db: Session = Depends(get_db)) -> System:
    system = db.query(System).filter(System.slug == system_slug).first()
    if not system:
        raise HTTPException(404, "System not found")
    return system
```

### 4.3 Webhook Router (multi-system)

Replace single `/webhooks/n8n` with per-system routing:

```
POST /webhooks/{system_slug}
```

HMAC secret resolved from DB (`system.webhook_secret`), not env var. Fallback: existing `N8N_WEBHOOK_SECRET` env var for `esteps-leads`.

### 4.4 New Admin Endpoints

```
GET  /admin/systems                     → list all active systems
GET  /admin/systems/overview            → cross-system KPIs + recent executions
GET  /admin/systems/{slug}              → single system stats
GET  /admin/systems/{slug}/executions   → paginated execution history
```

Existing endpoints untouched:
```
GET  /admin/dashboard/metrics           → eSteps leads KPIs (unchanged)
GET  /admin/workflows/status            → eSteps workflow status (unchanged)
```

### 4.5 n8n API Proxy

```
GET  /proxy/n8n/workflows               → list n8n workflows (via n8n REST API)
POST /proxy/n8n/workflows/{id}/execute  → trigger n8n workflow
```

Uses `N8N_API_KEY` + `N8N_BASE_URL` env vars. Prevents CORS/credential exposure on frontend.

---

## 5. Frontend Architecture

### 5.1 State: Pinia + URL sync

`useSystemStore` = source of truth. URL stays synced (not primary source).

```javascript
// stores/system.js
export const useSystemStore = defineStore('system', () => {
  const systems = ref([])
  const activeSystemSlug = ref(null)  // null = "all systems" overview

  function setActive(slug) { activeSystemSlug.value = slug }
  async function loadSystems() { ... }
  return { systems, activeSystemSlug, setActive, loadSystems }
})
```

Router `beforeEach` guard syncs `?system=slug` param → store. Store watcher syncs → URL.

### 5.2 New Views

```
/systems              → SystemsOverview.vue  (cross-system KPI grid)
/systems/:slug        → SystemDetail.vue     (per-system executions + stats)
```

Existing views (`/overview`, `/pipeline`, `/workflows`, `/ai`, `/system`) unchanged.

### 5.3 System Selector Component

`SystemSelector.vue` in sidebar — dropdown of active systems + "All Systems" option. Updates `useSystemStore.activeSystemSlug`.

---

## 6. Error Handling

- Unknown `system_slug` in webhook → 404, log warning, reject payload
- HMAC mismatch → 403, log to `audit_logs` with `system_id`
- n8n proxy unreachable → 503 with `{"error": "n8n unavailable"}`
- Cross-system overview: partial failures per system are isolated (one bad system doesn't fail the whole endpoint)

---

## 7. Testing Strategy

- Unit: `SystemService.get_cross_system_overview()` with fixture data
- Integration: POST `/webhooks/esteps-leads` with valid + invalid HMAC
- Integration: GET `/admin/systems/overview` returns all system slugs
- Frontend: `useSystemStore` URL sync round-trip
- No E2E added in this sprint (existing E2E coverage preserved)

---

## 8. Implementation Phases

| Phase | What | Gate |
|-------|------|------|
| 1 | Alembic migration `0002` + `System` model | ✓ before all else |
| 2 | `SystemService` + `get_system` dependency | ✓ tests pass |
| 3 | Webhook router multi-system | ✓ HMAC works both old + new |
| 4 | Admin endpoints (list, overview, per-system) | ✓ returns data |
| 5 | n8n API proxy | ✓ proxies correctly |
| 6 | Frontend `useSystemStore` + URL sync | ✓ no regressions |
| 7 | `SystemsOverview.vue` + `SystemDetail.vue` | ✓ renders correctly |
| 8 | `SystemSelector.vue` in sidebar | ✓ existing views unbroken |

Phases 1-5 backend, 6-8 frontend. All phases non-breaking on existing endpoints.
