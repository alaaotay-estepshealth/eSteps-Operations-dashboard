<template>
  <div class="space-y-3">
    <div v-if="messages.length" class="space-y-3 max-h-96 overflow-y-auto">
      <div v-for="(m, i) in messages" :key="i" class="flex" :class="m.role === 'user' ? 'justify-end' : 'justify-start'">
        <div
          class="max-w-[85%] rounded px-3 py-2 text-xs"
          :class="m.role === 'user'
            ? 'bg-status-info-bg text-status-info border border-status-info'
            : 'bg-ctrl-panel text-ctrl-text border border-ctrl-border'"
        >
          <pre v-if="m.role === 'assistant'" class="whitespace-pre-wrap font-sans leading-relaxed">{{ m.text }}</pre>
          <span v-else>{{ m.text }}</span>
        </div>
      </div>
      <div v-if="loading" class="flex justify-start">
        <div class="bg-ctrl-panel border border-ctrl-border rounded px-3 py-2 text-xs text-ctrl-dim animate-pulse">Thinking…</div>
      </div>
    </div>

    <div v-if="!messages.length" class="flex flex-wrap gap-2">
      <button v-for="s in suggestions" :key="s" @click="ask(s)"
        class="text-2xs border border-ctrl-border rounded px-2.5 py-1 text-ctrl-muted hover:text-ctrl-text hover:border-ctrl-raised transition-all">
        {{ s }}
      </button>
    </div>

    <form @submit.prevent="ask(input)" class="flex gap-2">
      <input v-model="input" type="text" placeholder="Ask about the pipeline…"
        class="flex-1 bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-3 py-2 focus:outline-none focus:border-status-info placeholder-ctrl-dim" />
      <button type="submit" :disabled="loading || !input.trim()"
        class="flex items-center gap-1.5 text-xs border border-status-info text-status-info rounded px-3 py-2 hover:bg-status-info-bg disabled:opacity-40 transition-all">
        <Send class="w-3.5 h-3.5" /> Ask
      </button>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Send } from 'lucide-vue-next'
import { adminAPI } from '../api/index.js'

const messages = ref([])
const input    = ref('')
const loading  = ref(false)

const suggestions = [
  'Which hot leads should I contact today?',
  'Why is the reply rate below target?',
  'What should I focus on this week?',
]

async function ask(question) {
  const q = (question || '').trim()
  if (!q || loading.value) return
  messages.value.push({ role: 'user', text: q })
  input.value = ''
  loading.value = true
  try {
    const { data } = await adminAPI.askAssistant(q)
    messages.value.push({ role: 'assistant', text: data.answer })
  } catch (e) {
    messages.value.push({ role: 'assistant', text: e.response?.data?.detail || 'Could not answer right now.' })
  } finally {
    loading.value = false
  }
}
</script>
