# eSteps Ops Decision-Helper — Design

**Date**: 2026-05-26
**Status**: Approved — implementing (Approach A: one spec, 4 shippable phases)

---

## 1. Goal

Evolve the ES-OPS-09 dashboard from a monitoring board into a decision-helper that shows results, helps the team decide, surfaces emails + contacted people + hot leads, reminds about follow-ups and meeting dates, compares results week/month/vs-goals, and recommends strategy/fixes/focus — grounded in the GTM strategy targets.

## 2. GTM targets (baselines for KPIs & recommendations)

Reply rate > 8% · Meeting-booked rate > 3% · Open rate > 35% · 100–150 leads/week · lead→pilot > 15% · pilot→customer > 60% · score ≥ 7 = hot/MQL (24h handoff). 5-touch sequence: Day 1 email / 3 LinkedIn / 7 email / 14 DM / 21 break-up / 30 nurture. Decision levers: reply<8% → tighten ICP + personalize; meeting<3% → free-asset specificity; open<35% → subject/domain.

## 3. Data reality (drives graceful-empty design)

`leads.reply_received` / `meeting_booked_at` are empty — real replies live in `conversations` (inbound); meetings are derived. Strong live signals: 390 overdue follow-ups, 287 hot leads uncontacted, sequence drop 464→234 after touch 3, 0 outreach in last 7 days. Views must lead with strong signals and degrade gracefully where data is sparse.

## 4. Architecture

Extend existing patterns: one FastAPI router per concern, one Vue view per surface, reuse `useStaleFetch`, role-gating, audit-logging. Charts = inline-SVG components (no heavy deps). Hybrid AI = deterministic rule engine (`insights.py`) + optional Gemini narrative behind a dedicated endpoint. Sources: leads DB (`leads`, `conversations`) + ops DB (`workflow_executions`, `ai_requests`, `audit_logs`).

## 5. Phases

### Phase 1 — Strategy Insights (polish; partly built)
`/insights` + `GET /admin/insights` already live. Add month-over-month comparison, goal progress (toward 30–50 partnerships / pilots), a trend `LineChart`, clickable chart bars → filtered Contacts. impeccable layout pass.

### Phase 2 — Follow-ups & Calendar
`GET /admin/followups` → `{ overdue, due_today, this_week, upcoming_meetings, hot_needs_action }` (leads DB). `FollowupsView.vue` (`/followups`) with those sections; row → contact timeline; quick **Reschedule/Done** via existing `lead_actions` (pause/resume), operator+admin gated. Replaces the `/pipeline` placeholder links in Insights.

### Phase 3 — Contacts & Hot Leads
`GET /admin/contacts` (paginated; filters hot/stage/area/replied/score) → name, institution, position, score, touches-sent, last-contacted, replied?, stage. `GET /admin/contacts/{lead_id}` → detail + timeline (email1-5 sent, inbound replies w/ body, meeting dates, stage). `ContactsView.vue` (`/contacts`) — searchable table + Hot toggle (score≥7) + row → detail drawer + quick actions. Hot leads = the Hot filter. Target of Insights/segment drill-downs.

### Phase 4 — AI Strategy Memo (hybrid)
`POST /admin/insights/memo` — feeds rule-engine facts to Gemini 2.5 Flash (via httpx REST, no new dep) → narrative memo (strategy, predicted risks, fixes, weekly focus). New `GEMINI_API_KEY` setting; missing key → friendly 503. Admin-only. Insights view gets a "Generate strategy memo" button rendering the markdown.

## 6. Charts & clickability (cross-cutting)

`BarChart` (done) + new `LineChart` (trends) + `DonutChart` (distributions); all SVG/OKLCH, clickable via `emit('select')`. Drill-downs: KPI card → filtered view; chart bar → filtered Contacts; table row → detail drawer; segment bar → Contacts by research area.

## 7. Cross-cutting concerns

Role gating (reads open to all; writes operator/admin). Graceful empty states everywhere. Gemini failures isolated (503, never crash a page). Write actions audit-logged. Rule-engine helpers kept pure for unit tests (run once `TEST_DATABASE_URL` set; conftest guard already prevents prod-DB wipe). impeccable craft applied at implementation for the control-room feel.

## 8. Navigation (post-build)

```
Operations: All Systems · Overview · Insights
Pipeline:   Pipeline · Contacts · Email Analytics · Bookings · Deals · Follow-ups
Automation: Workflows · n8n Workflows · AI Monitor · Review
Strategy:   Tickets · GTM Strategy · System Logs · Report
```

## 9. New / changed files

**Backend:** extend `routers/insights.py` (+month, +goals, +memo); new `routers/followups.py`; new `routers/contacts.py`; `config.py` (+`gemini_api_key`); register in `main.py`.
**Frontend:** new `views/FollowupsView.vue`, `views/ContactsView.vue`; new `components/ui/LineChart.vue`, `components/ui/DonutChart.vue`; extend `views/Insights.vue`; `api/index.js`, `router/index.js`, `Sidebar.vue`, `TopBar.vue`.

## 10. Verification

Per phase: backend import OK, live endpoint smoke test (read-only), frontend `vite build` clean. Write actions tested via safe round-trip (capture→act→restore) as in prior work.
