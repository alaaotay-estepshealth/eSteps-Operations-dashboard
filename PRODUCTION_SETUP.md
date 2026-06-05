# eSteps Ops Dashboard — Production Setup & Real-Data Integration

End-to-end guide for taking the dashboard from seeded demo state to live, real-data production. Every env var, every n8n hook, every external integration — ordered by impact.

---


## 🔌 Linking to Real Data — Complete Checklist

Below is every env var, n8n hook, and external integration **in order of impact**. Severity flags:

- 🔴 **Actually breaks features** — must fix before going live
- 🟡 **Degrades UX** — some views show 503 / empty until set
- 🟢 **Polish only** — safe to defer

### 1. ✅ Leads Database (Supabase) — DONE

This is the **single biggest factor**. The Briefing, Insights, Pipeline, Contacts, Followups, and Email Analytics views all read from the leads DB (separate from ops DB). If `LEADS_DATABASE_URL` is empty, the code silently falls back to ops DB which has no `leads` table → 500s or zero values everywhere.

Edit `backend/.env`:

```env
LEADS_DATABASE_URL=postgresql://<user>:<pw>@<host>:5432/<db>?sslmode=require
```

Use the **read-only** connection string from your eSteps Leads Supabase project (eu-central-1). The dashboard never writes to it.

**Verify:** Briefing page shows non-zero numbers under "Overdue follow-ups" / "Hot uncontacted" — if you already see e.g. 553 / 154, this is set correctly ✅.

### 2. 🔴 n8n Webhooks — Push real execution data

The dashboard **never polls n8n** for execution status. It only sees what n8n POSTs to its webhooks.

**Two endpoints per system, with HMAC headers:**

| Endpoint | Who posts | What it fills |
|---|---|---|
| `POST /webhooks/{slug}` | EST-2, EST-3, EST-5 (every workflow at the end of its run) | Workflows view, Overview workflow tiles, Activity Feed, daily chart |
| `POST /webhooks/{slug}/ai-decision` | EST-3 reply handler, EST-8 lead scoring, any AI step | AI Monitor, Review Queue, Overview AI KPIs |

**Required headers:**

```
Content-Type: application/json
X-N8N-Signature: sha256=<HMAC_SHA256(body, system.webhook_secret)>
```

**Where the secret lives:** in the DB column `systems.webhook_secret` (one per system slug). The seed creates them:

```
esteps-leads-secret-change-me
wam-agency-secret-change-me
ai-chatbot-secret-change-me
solar-leads-secret-change-me
ai-influencer-secret-change-me
```

**Change them before production:**

```sql
UPDATE systems SET webhook_secret = '<random-32-char>' WHERE slug = 'esteps-leads';
-- repeat for each system slug
```

**In n8n** (per workflow, final node = HTTP Request):

```
Method: POST
URL:    https://<your-backend>/webhooks/esteps-leads
Body (JSON):
{
  "workflow_id":      "{{$workflow.id}}",
  "workflow_name":    "{{$workflow.name}}",
  "execution_id":     "{{$execution.id}}",
  "status":           "{{$json.success ? 'success' : 'failed'}}",
  "duration_seconds": {{$execution.duration / 1000}},
  "error_message":    "{{$json.error || null}}"
}
Headers:
  X-N8N-Signature: sha256={{$crypto.createHmac('sha256','<secret>').update(JSON.stringify($json)).digest('hex')}}
```

**For AI decisions** (separate HTTP node after every Gemini/OpenAI call):

```
URL: https://<your-backend>/webhooks/esteps-leads/ai-decision
Body (JSON):
{
  "request_type":      "lead_classify",          // or email_summarize | priority_score | draft_reply | chatbot_reply
  "workflow_source":   "EST-3: Reply Handler",
  "decision_id":       "{{$execution.id}}-{{$item.index}}",   // idempotency key
  "entity_id":         "{{$json.lead_id}}",
  "entity_type":       "lead",
  "provider":          "gemini",
  "model":             "gemini-1.5-flash",
  "tokens_used":       {{$json.usage.total_tokens}},
  "cost_usd":          {{$json.cost}},
  "latency_ms":        {{$json.latency}},
  "input_preview":     "{{$json.input.substring(0,200)}}",
  "ai_output":         {{ $json.output }},
  "confidence_score":  {{$json.confidence}}
}
```

Decisions with `confidence_score < 0.70` **auto-route to the Review Queue**.

#### Step-by-step wiring (plain language)

1. Rotate the per-system HMAC secret in the ops DB:

   ```sql
   UPDATE systems SET webhook_secret = '<random-32-char>' WHERE slug = 'esteps-leads';
   ```

2. For each workflow that should log a run (EST-2, EST-3, EST-5), add two nodes at the very end:

   **Set node** (name it `Build webhook payload`):

   ```json
   {
     "workflow_id": "={{$workflow.id}}",
     "workflow_name": "={{$workflow.name}}",
     "execution_id": "={{$execution.id}}",
     "status": "={{$json.success ? 'success' : 'failed'}}",
     "duration_seconds": "={{$execution.duration / 1000}}",
     "error_message": "={{$json.error || null}}"
   }
   ```

   **HTTP Request node** (name it `POST run to dashboard`):

   - Method: `POST`
   - URL: `https://<your-backend>/webhooks/esteps-leads`
   - Body: JSON (send the entire Set node output)
   - Headers:
     - `Content-Type`: `application/json`
     - `X-N8N-Signature`: `={{'sha256=' + $crypto.createHmac('sha256','<secret>').update(JSON.stringify($json)).digest('hex')}}`

   If your workflow does not have `$json.success` or `$json.error`, replace those with the correct fields in your flow.

3. For each AI step (EST-3 reply handler, EST-8 lead scoring, any AI call), add two nodes right after the AI node:

   **Set node** (name it `Build AI decision payload`):

   ```json
   {
     "request_type": "lead_classify",
     "workflow_source": "EST-3: Reply Handler",
     "decision_id": "={{$execution.id}}-{{$item.index}}",
     "entity_id": "={{$json.lead_id}}",
     "entity_type": "lead",
     "provider": "gemini",
     "model": "gemini-1.5-flash",
     "tokens_used": "={{$json.usage.total_tokens}}",
     "cost_usd": "={{$json.cost}}",
     "latency_ms": "={{$json.latency}}",
     "input_preview": "={{$json.input.substring(0,200)}}",
     "ai_output": "={{$json.output}}",
     "confidence_score": "={{$json.confidence}}"
   }
   ```

   **HTTP Request node** (name it `POST AI decision`):

   - Method: `POST`
   - URL: `https://<your-backend>/webhooks/esteps-leads/ai-decision`
   - Body: JSON (send the entire Set node output)
   - Headers: same as step 2

4. If the backend is local, use a public URL (ngrok/cloudflared). n8n cannot POST to `localhost`.

5. Test: click **Execute Node** on the HTTP Request node. Expect HTTP 200.

### 3. ✅ Gemini — Strategy memo + Ask-the-Assistant — DONE

```env
GEMINI_API_KEY=AIza...
```

Get from [Google AI Studio](https://aistudio.google.com/apikey). If you only have access to 1.5, change model name in `backend/app/routers/insights.py:273,297` from `gemini-2.5-flash` → `gemini-1.5-flash`.

**What breaks without it:** Insights view "Generate strategy memo" button → 503. Briefing page memo block stays empty. Ask-the-Assistant returns 503.

### 4. ✅ n8n API key — Live workflow control — DONE

```env
N8N_BASE_URL=https://n8n.estepshealth.tech
N8N_API_KEY=<n8n personal access token>
```

Generate in n8n: **Settings → API → Create API Key**.

**What breaks without it:** `/n8n` view's Trigger / Activate / Deactivate buttons return 503. The workflow list is empty. `POST /admin/sync-n8n` fails (so the workflow registry stays out of date).

### 5. 🟢 OpenClaw — Agent action launcher (optional)

```env
OPENCLAW_BASE_URL=https://openclaw.estepshealth.tech
OPENCLAW_HOOK_TOKEN=<bearer token from OpenClaw>
```

**In OpenClaw:** set `hooks.enabled = true` and create a dedicated `hooks.token`.

**What breaks without it:** `/agent` view loads but actions return 503. Safe to skip for v1.

### 6. 🔴 Production security must-fixes

| | Status |
|---|---|
| `JWT_SECRET` rotated to random 32+ char hex | ✅ done |
| `AUTO_CREATE_DB=false` | ✅ done |
| `ENVIRONMENT=production` | ❌ still `development` — flip before go-live (enables HMAC enforcement; hides `/webhooks/n8n/simulate`) |
| `CORS_ORIGINS` restricted to prod frontend | ❌ still `localhost:5173,localhost:3000` — add prod origin |

Reminders:
- **`ENVIRONMENT ≠ production`** → HMAC enforcement is skipped (missing signatures pass) and `/webhooks/n8n/simulate` stays exposed.
- **`AUTO_CREATE_DB=true` in prod** → drift from Alembic migrations.

### 7. 🟢 Gmail — already handled by n8n

The dashboard has **zero Gmail integration** — that's intentional. EST-2 (sending) and EST-3 (replies) handle OAuth, sending, IMAP/Pub-Sub in n8n. The dashboard sees only the outcomes via `/webhooks/{slug}` + the `email_logs` table.

So for "real Gmail data": fix it in n8n, not here. Email Analytics view fills automatically once EST-2 logs sends/opens/bounces to the `email_logs` table.

---

## 📋 Final Pre-Launch Checklist

Copy this to a checklist tool. Mark off in order.

### Infra (Backend)

- [x] `.env`: `LEADS_DATABASE_URL` set to Supabase read-only conn string
- [x] `.env`: `GEMINI_API_KEY` set
- [x] `.env`: `N8N_API_KEY` set
- [x] `.env`: `JWT_SECRET` rotated to random 32+ char string
- [ ] `.env`: `ENVIRONMENT=production`
- [x] `.env`: `AUTO_CREATE_DB=false`
- [ ] `.env`: `CORS_ORIGINS` restricted to prod frontend origin
- [ ] DB: `UPDATE systems SET webhook_secret = <new random>` for each slug
- [x] DB: Test login `admin / admin123` → footer reads ADMIN / Full access
- [ ] DB: Rotate seed passwords (`admin123` / `operator123` / `viewer123`) before prod

### Integration (n8n — eSteps Leads)

- [ ] EST-1 workflow → POST `/webhooks/esteps-leads` on completion (HMAC)
- [ ] EST-2 outreach → POST `/webhooks/esteps-leads` on completion (HMAC)
- [ ] EST-3 reply → POST `/webhooks/esteps-leads` on completion (HMAC)
- [ ] EST-3 reply → POST `/webhooks/esteps-leads/ai-decision` per classification (HMAC)
- [ ] EST-5 booking sync → POST `/webhooks/esteps-leads` on completion (HMAC)
- [ ] EST-8 lead scoring → POST `/webhooks/esteps-leads/ai-decision` per scored lead

### Integration (other 4 systems, if relevant)

- [ ] `wam-agency` workflows wired to its slug
- [ ] `ai-chatbot` workflows wired to its slug
- [ ] `solar-leads` workflows wired to its slug
- [ ] `ai-influencer` workflows wired to its slug

### Verification (click each view, in order)

- [ ] `/briefing` — non-zero "since yesterday" + "today's priorities"
- [ ] `/insights` — recommendations populated; click "Generate strategy memo" → memo text returned
- [ ] `/pipeline` — 972 lead rows, filters work
- [ ] `/contacts` — search works, click into a person → timeline drawer loads
- [ ] `/followups` — overdue queue shows real leads
- [ ] `/emails` — delivery/open/bounce > 0 (requires EST-2 sends recorded)
- [ ] `/bookings` — meetings show real data from EST-5
- [ ] `/workflows` — 14-day chart shows real n8n runs (not seeded)
- [ ] `/n8n` — live workflow list loads; trigger button works
- [ ] `/ai` — AI decisions show real provider + cost (not seeded)
- [ ] `/review` — pending items have real input previews from EST-3
- [ ] `/agent` — Status shows `configured: true` (only if `OPENCLAW_*` set)
- [ ] `/gtm` — strategy markdown files load from `STRATEGY_DIR`
- [ ] `/system` — audit log shows real `/admin/*` POSTs from your usage
- [ ] `/report` — print preview renders cleanly with real numbers

### Polish

- [ ] **Seed cleanup**: optionally delete the 350 seeded `ai_requests` + 500 seeded `workflow_executions` before real n8n data flows in to avoid mixed signals.

  ```sql
  DELETE FROM ai_requests        WHERE workflow_source IN ('fastapi', 'ai_service');
  DELETE FROM workflow_executions WHERE correlation_id LIKE 'corr_%';
  ```

- [ ] Replace seed passwords (`admin123` etc.) with strong unique passwords.
- [ ] Set up nightly backup of ops DB (`workflow_executions` + `audit_logs` are the only stateful data — everything else can be re-derived from leads DB).

---

## 🚀 Restart Sequence

Apply every change above by restarting both servers cleanly. **Stop both servers first** (Ctrl+C in their windows), then:

**Window 1 — backend:**

```powershell
cd "D:\dev\n8n-workflows\eSteps Lead Generation System\dashboard-system\backend"
uvicorn app.main:app --reload --port 8000
```

**Window 2 — frontend:**

```powershell
cd "D:\dev\n8n-workflows\eSteps Lead Generation System\dashboard-system\frontend"
Remove-Item -Recurse -Force node_modules\.vite -ErrorAction SilentlyContinue
npm run dev
```

Then **hard-refresh the browser** (Ctrl+Shift+R). You should see:

1. eSteps logo to the left of the wordmark (Sidebar + Login + browser tab favicon).
2. `/review` no longer 500s — shows the 71 pending items.
3. `/insights` "Generate memo" → actionable error message if Gemini key is wrong (or a real memo if it's right).

---

## 📚 Related docs

- [`README.md`](README.md) — system overview + 21 dashboard routes
- [`backend/.env.example`](backend/.env.example) — every env var with defaults
- [`docs/PRODUCT.md`](docs/PRODUCT.md) — product principles + design system rules
- [`docs/DESIGN.md`](docs/DESIGN.md) — Control Room Minimalism palette + typography

---

## ✅ Current Readiness Snapshot — 2026-06-02

Dashboard enhancements from the project meeting (PFE ES-OPS-09 review):

| # | Item from meeting PDF | Status |
|---|---|---|
| 1 | RBAC: sidebar items change per role | ✅ admin (20) / operator (16) / readonly (12) |
| 2 | RBAC: route-level enforcement | ✅ `meta.roles` + `beforeEach` (redirect to `/briefing` if denied) |
| 3 | Review Queue actions | ✅ Approve / Reject / Override differentiated (DB status + audit log) — operator can resolve, not admin-only |
| 4 | Contacts row-click popup | ✅ Drawer shows LinkedIn link, phone, website, department, publications, notes — backend uses `to_jsonb` so missing upstream columns return NULL instead of 500 |
| 5 | GTM file explorer + uploader | ✅ Recursive tree, drag-drop upload, folder upload, new folder, delete, download — uploads persist in DB (`strategy_assets` table) and survive restarts. Disk roots walked with depth/noise caps so /tree responds in <2s on huge repos |
| — | 401 reload loop after logout | ✅ Interceptor no longer redirects when already on `/login`; AlertBanner skips polling when no token |

### Production env state (`backend/.env`)

| Severity | Item | State |
|---|---|---|
| 🟢 | `DATABASE_URL` (ops Supabase, eu-west-1) | ✅ set |
| 🟢 | `LEADS_DATABASE_URL` (leads Supabase, eu-central-1) | ✅ set — Briefing / Contacts / Pipeline show real data |
| 🟢 | `JWT_SECRET` | ✅ 32-byte random hex (not the dev default) |
| 🟢 | `JWT_EXPIRE_MINUTES=1440`, `AUTO_CREATE_DB=false` | ✅ |
| 🟢 | `GEMINI_API_KEY` | ✅ set — strategy memo + assistant work |
| 🟢 | `N8N_API_KEY` (Bearer) | ✅ set — `/n8n` view works |
| 🟢 | `STRATEGY_DIR` | ✅ pointed at 4 real roots (GTM engeneering / Mitus / AI Medicine Agent ROBOSAN / eSteps Health - care platform). DB-backed `uploads` root is auto-created on first request |
| 🟡 | `CORS_ORIGINS` | only `localhost` — add prod frontend before going live |
| 🟡 | `N8N_WEBHOOK_SECRET` (per-system, DB column) | still the seed defaults (`*-secret-change-me`) — rotate per §2 above |
| 🟡 | seed passwords (`admin123` / `operator123` / `viewer123`) | rotate before prod |
| 🔴 | `ENVIRONMENT=development` | flip to `production` for go-live (enables HMAC enforcement, hides `/webhooks/n8n/simulate`) |
| ⚪ | `OPENCLAW_BASE_URL` / `OPENCLAW_HOOK_TOKEN` | not set — `/agent` view returns 503 (optional per spec) |

**Verdict** — green for development with real data. The four 🟡/🔴 items are pure config rotations, no code work, and are the only blockers for prod hand-off.
