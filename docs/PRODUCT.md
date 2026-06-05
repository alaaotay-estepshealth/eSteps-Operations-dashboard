# Product

## Register

product

## Users

eSteps Health operations team (1-5 people). Primary user: a solo operator checking the dashboard in the morning to review overnight workflow runs, assess which leads need human attention, and track outreach campaign progress. Works on a laptop or desktop monitor in a focused, task-oriented context. Not a casual visitor; arrives with specific questions and needs fast, high-signal answers.

## Product Purpose

AI-powered lead generation operations control center. Tracks 972 academic researchers through a 5-touch outreach pipeline (new, introduced, pitching, call_requested, cold), monitors n8n workflow executions, surfaces AI decision confidence and human review queues, and logs all system activity. Success = operator makes better decisions faster and never misses a bottleneck.

## Operational Strategy (Best Practice)

1. **n8n is the source of truth for Gmail + workflow runs.** The dashboard never polls Gmail or n8n directly.
2. **Push everything into the ops DB via webhooks.** Every workflow ends with `POST /webhooks/{slug}`; every AI step posts decisions to `POST /webhooks/{slug}/ai-decision`.
3. **Lead data is read-only in the dashboard.** n8n writes `email_logs`, `conversations`, and `opportunities` in the leads Supabase DB; the dashboard only reads. Carve-out: the dashboard writes operator-authored meeting prep (`bookings` + `meeting_notes` + `meeting_tasks` in the **ops** DB) — these are operator artefacts, not lead-pipeline state, so they live alongside `audit_logs` rather than in the leads source.
4. **EST-3 is the reply hub.** It should log inbound/outbound emails to the leads DB, then post AI decision metadata (confidence, model, cost, latency) to the ops webhook.
5. **Reliability over elegance.** Use HMAC per system, retry webhook posts, and dedupe using `execution_id` / `decision_id`. Keep data freshness visible to the operator.

## Brand Personality

Precise, Focused, Trustworthy. Voice is direct and informative: no marketing speak, no decorative noise. Every element earns its place by conveying signal. Feels like a professional instrument, not a product demo.

## Anti-references

- Generic SaaS dark blue (Linear, Vercel, Raycast aesthetic)
- Clinical white healthcare UI (sterile, cold)
- Data-dense chaotic dashboards (Grafana, Bloomberg terminal)
- "AI magic" flashy interfaces (neon accents, animated blobs, gradient overload)
- Marketing-style dashboards (big vanity numbers, celebration UI)

## Design Principles

1. **Signal over decoration.** Every visual element communicates data or structure. Decorative elements that carry no information are removed.
2. **Hierarchy through restraint.** Importance is shown by scale and weight contrast, not by color saturation or glow effects.
3. **Instrument, not product.** The interface should feel like calibrated equipment: consistent, reliable, functional. Operators trust it because it never surprises them.
4. **Status is the primary language.** Color is reserved for status communication (healthy, warning, error, pending). It is never used decoratively.
5. **Density with breathing room.** Information is dense where it needs to be, but spacing is intentional, not uniform. Sections breathe; data rows are compact.

## Accessibility & Inclusion

WCAG AA minimum. All status colors must pass contrast in combination with dark background. No information conveyed by color alone (always paired with icon or label). Reduced motion: no animations that loop or distract during active use.
