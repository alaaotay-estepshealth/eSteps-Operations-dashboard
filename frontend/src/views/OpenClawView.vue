<template>
  <div class="space-y-8 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <!-- Not configured -->
    <SectionContainer v-if="!status.configured" title="OpenClaw Agent" subtitle="Launch actions on your systems through the OpenClaw agent">
      <div class="space-y-3 text-sm text-ctrl-muted">
        <p>Not connected yet. To link the dashboard to your OpenClaw agent:</p>
        <ol class="list-decimal list-inside space-y-1 text-xs">
          <li>In OpenClaw, enable hooks: <code class="text-ctrl-text">hooks.enabled = true</code> and set a dedicated <code class="text-ctrl-text">hooks.token</code>.</li>
          <li>In <code class="text-ctrl-text">backend/.env</code> set <code class="text-ctrl-text">OPENCLAW_BASE_URL=https://openclaw.estepshealth.tech</code> and <code class="text-ctrl-text">OPENCLAW_HOOK_TOKEN=&lt;that token&gt;</code>.</li>
          <li>Restart the backend.</li>
        </ol>
        <p class="text-2xs text-ctrl-dim">Uses OpenClaw's documented <code>/hooks/agent</code> + <code>/hooks/wake</code> webhook API (Bearer-token auth).</p>
      </div>
    </SectionContainer>

    <template v-else>
      <!-- Launch action -->
      <SectionContainer title="Launch an Agent Action" subtitle="Send an instruction to OpenClaw — it can act on DBs, email, CRM, drive">
        <div v-if="!isAdmin" class="text-xs text-ctrl-dim">Admin only — agent actions are restricted.</div>
        <div v-else class="space-y-3">
          <div class="flex flex-wrap gap-2">
            <button v-for="p in prompts" :key="p" @click="message = p"
              class="text-2xs border border-ctrl-border rounded px-2.5 py-1 text-ctrl-muted hover:text-ctrl-text hover:border-ctrl-raised transition-all">{{ p }}</button>
          </div>
          <textarea v-model="message" rows="3" placeholder="e.g. Enrich the top 10 hot uncontacted leads and draft a first-touch email for each"
            class="w-full bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-2 focus:outline-none focus:border-status-info placeholder-ctrl-dim" />
          <div class="flex items-center justify-between">
            <span class="text-2xs text-ctrl-dim">The agent acts on real systems. Every action is audit-logged.</span>
            <button @click="launch" :disabled="running || !message.trim()"
              class="flex items-center gap-2 text-xs border border-status-warn text-status-warn rounded px-3 py-2 hover:bg-status-warn-bg disabled:opacity-40 transition-all">
              <Bot class="w-3.5 h-3.5" :class="{ 'animate-pulse': running }" />
              {{ running ? 'Agent working…' : 'Launch action' }}
            </button>
          </div>
        </div>
      </SectionContainer>

      <!-- Result -->
      <SectionContainer v-if="result || resultError" title="Agent Response" subtitle="Result of the last action">
        <div v-if="resultError" class="text-xs text-status-err">{{ resultError }}</div>
        <pre v-else class="text-xs text-ctrl-text whitespace-pre-wrap font-sans leading-relaxed">{{ result }}</pre>
      </SectionContainer>
    </template>

  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { AlertCircle, Bot } from 'lucide-vue-next'
import { openclawAPI } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import SectionContainer from '../components/ui/SectionContainer.vue'

const auth        = useAuthStore()
const isAdmin     = computed(() => auth.role === 'admin')
const status      = ref({ configured: false, base_url: null })
const message     = ref('')
const result      = ref('')
const resultError = ref('')
const running     = ref(false)
const error       = ref('')

const prompts = [
  'Summarize this week\'s pipeline and recommend where to focus',
  'Enrich the top 10 hot uncontacted leads',
  'Draft first-touch emails for the overdue follow-up queue',
  'Check which leads replied this week and suggest next steps',
]

async function launch() {
  const msg = message.value.trim()
  if (!msg) return
  if (!window.confirm('Send this instruction to the OpenClaw agent? It can act on your DBs, email, CRM and drive.')) return
  running.value = true
  result.value = ''
  resultError.value = ''
  try {
    const { data } = await openclawAPI.runAgent({ message: msg })
    result.value = typeof data.result === 'string' ? data.result : JSON.stringify(data.result, null, 2)
  } catch (e) {
    resultError.value = e.response?.data?.detail || 'Agent action failed.'
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  try {
    const { data } = await openclawAPI.status()
    status.value = data
  } catch {
    error.value = 'Failed to reach OpenClaw status.'
  }
})
</script>
