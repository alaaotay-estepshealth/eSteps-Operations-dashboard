/**
 * n8n Code node — HMAC-signed callback to ES-OPS-09 backend
 *
 * Add this as the LAST node in each n8n workflow.
 * Follow with an "HTTP Request" node (config below).
 *
 * ── PER-WORKFLOW CONFIG ────────────────────────────────────────────────────
 * Change these 4 values for each workflow:
 */
const BACKEND_URL  = 'https://ops-api.estepshealth.tech';  // or http://localhost:8000
const SYSTEM_SLUG  = 'esteps-leads';   // must match systems.slug in DB
const HMAC_SECRET  = 'esteps-leads-secret-change-me';  // match systems.webhook_secret in DB
const WORKFLOW_ID  = 'est-2';          // short id for this workflow
const WORKFLOW_NAME = 'EST-2: Outreach Engine';  // display name
// ──────────────────────────────────────────────────────────────────────────

const crypto = require('crypto');

const itemsIn = $input.all();
const lastItem = itemsIn[itemsIn.length - 1]?.json ?? {};

// Detect error from upstream nodes
const hasError = lastItem?.error != null;

const payload = {
  workflow_id: WORKFLOW_ID,
  workflow_name: WORKFLOW_NAME,
  execution_id: $execution.id,
  status: hasError ? 'failed' : 'success',
  duration_seconds: null,
  error_message: hasError ? String(lastItem.error) : null,
  error_type: hasError ? 'workflow_error' : null,
  correlation_id: `n8n-${$execution.id}`,
  metadata: {
    items_processed: itemsIn.length,
    system_slug: SYSTEM_SLUG,
  },
};

const body = JSON.stringify(payload);
const sig = `sha256=${crypto.createHmac('sha256', HMAC_SECRET).update(body).digest('hex')}`;

return [{
  json: {
    url: `${BACKEND_URL}/webhooks/${SYSTEM_SLUG}`,
    body,
    sig,
  },
}];

/**
 * ── HTTP REQUEST NODE CONFIG (add after this Code node) ───────────────────
 *
 * Method:             POST
 * URL:                ={{ $json.url }}
 * Body Content Type:  Raw
 * Raw Body:           ={{ $json.body }}
 *
 * Headers:
 *   Content-Type:       application/json
 *   x-n8n-signature:    ={{ $json.sig }}
 *
 * ── SYSTEM SLUG → HMAC SECRET MAPPING ────────────────────────────────────
 *
 * esteps-leads   →  set in seed.py (change in DB: UPDATE systems SET webhook_secret=... WHERE slug='esteps-leads')
 * wam-agency     →  wam-agency-secret-change-me
 * ai-chatbot     →  ai-chatbot-secret-change-me
 * solar-leads    →  solar-leads-secret-change-me
 * ai-influencer  →  ai-influencer-secret-change-me
 */
