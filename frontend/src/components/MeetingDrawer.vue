<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
      @click="$emit('close')"
    />
    <aside
      v-if="open"
      class="fixed top-0 right-0 z-50 h-full w-full md:w-[80vw] lg:w-[60vw] bg-ctrl-bg border-l border-ctrl-border flex flex-col"
    >
      <header class="flex items-center justify-between p-4 border-b border-ctrl-border">
        <div class="min-w-0">
          <div class="font-display text-sm text-ctrl-text truncate">
            {{ detail?.lead?.name || '…' }}
            <span v-if="detail?.lead?.institution" class="text-ctrl-muted">· {{ detail.lead.institution }}</span>
          </div>
          <div class="text-2xs text-ctrl-muted">
            <span v-if="detail?.booking?.scheduled_for">{{ whenLabel }}</span>
            <span v-if="detail?.booking?.rescheduled_from" class="ml-2 text-status-warn">
              Rescheduled from {{ fmt(detail.booking.rescheduled_from) }}
            </span>
          </div>
          <div v-if="detail?.previous_meetings?.length" class="text-2xs text-ctrl-dim mt-1">
            Previous: {{ detail.previous_meetings.length }} meeting{{ detail.previous_meetings.length === 1 ? '' : 's' }}
            (last {{ relPast(detail.previous_meetings[0].scheduled_for) }})
          </div>
        </div>
        <div class="flex items-center gap-2">
          <RouterLink
            v-if="bookingId"
            :to="`/meeting/${bookingId}`"
            class="px-2 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text"
          >Open full page ↗</RouterLink>
          <button class="px-2 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-ok" @click="markHeld">Mark held</button>
          <button class="px-2 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-err" @click="markNoShow">No-show</button>
          <button class="text-ctrl-muted hover:text-ctrl-text" @click="$emit('close')" aria-label="Close">×</button>
        </div>
      </header>

      <div class="flex items-center gap-1 px-4 pt-3 border-b border-ctrl-border">
        <button
          v-for="t in ['Prep', 'Recap', `Checklist ${doneCount}/${totalCount}`]"
          :key="t"
          @click="tab = t.split(' ')[0].toLowerCase()"
          :class="tab === t.split(' ')[0].toLowerCase()
            ? 'border-status-info text-ctrl-text'
            : 'border-transparent text-ctrl-muted hover:text-ctrl-text'"
          class="px-3 py-1.5 text-xs border-b-2 transition-colors"
        >{{ t }}</button>
      </div>

      <div class="flex-1 overflow-y-auto p-4 space-y-3">
        <div v-if="loading" class="text-xs text-ctrl-muted">Loading…</div>
        <div v-else-if="error" class="text-xs text-status-err">{{ error }}</div>
        <template v-else-if="detail">
          <div v-if="detail.notes?.ai_skipped === 'budget_exhausted'"
               class="text-2xs text-status-warn p-2 border border-status-warn/40 rounded">
            AI draft skipped — daily budget exhausted.
            <button v-if="isAdmin" class="ml-2 underline" @click="redraft(true)">Force redraft</button>
          </div>
          <div v-else-if="detail.notes?.ai_skipped === 'upstream_error'"
               class="text-2xs text-status-warn p-2 border border-status-warn/40 rounded">
            AI draft failed — Gemini upstream error.
            <button class="ml-2 underline" @click="redraft(false)">Retry</button>
          </div>

          <MeetingNoteEditor
            v-if="tab === 'prep'"
            v-model="prepDraft"
            placeholder="Prep notes…"
            :ai-drafted-at="detail.notes?.ai_drafted_at"
            :ai-model="detail.notes?.ai_model"
            :updated-by="detail.notes?.updated_by"
            @save="savePrep"
          />
          <MeetingNoteEditor
            v-else-if="tab === 'recap'"
            v-model="recapDraft"
            placeholder="What happened, what was agreed, next steps…"
            :updated-by="detail.notes?.updated_by"
            @save="saveRecap"
          />
          <div v-else class="space-y-1">
            <form @submit.prevent="addTask" class="flex items-center gap-2 mb-2">
              <input
                v-model="newTask"
                placeholder="+ Add task and press Enter"
                class="flex-1 bg-ctrl-panel border border-ctrl-border rounded px-3 py-1.5 text-sm text-ctrl-text focus:outline-none focus:border-status-info"
              />
            </form>
            <MeetingTaskRow
              v-for="t in detail.tasks"
              :key="t.id"
              :task="t"
              @toggle="(d) => toggleTask(t, d)"
              @rename="(n) => renameTask(t, n)"
              @delete="deleteTask(t)"
            />
            <div v-if="!detail.tasks.length" class="text-2xs text-ctrl-dim py-3">No tasks yet.</div>
          </div>
        </template>
      </div>
    </aside>
  </Teleport>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { meetingsAPI } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import MeetingNoteEditor from './MeetingNoteEditor.vue'
import MeetingTaskRow from './MeetingTaskRow.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  bookingId: { type: String, default: null },
})
const emit = defineEmits(['close', 'changed'])

const auth = useAuthStore()
const isAdmin = computed(() => auth.role === 'admin')

const tab = ref('prep')
const loading = ref(false)
const error = ref('')
const detail = ref(null)
const prepDraft = ref('')
const recapDraft = ref('')
const newTask = ref('')

const totalCount = computed(() => detail.value?.tasks?.length ?? 0)
const doneCount = computed(() => detail.value?.tasks?.filter(t => t.done).length ?? 0)
const whenLabel = computed(() => fmt(detail.value?.booking?.scheduled_for))

watch(() => [props.open, props.bookingId], async ([open, id]) => {
  if (open && id) await load()
}, { immediate: true })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await meetingsAPI.get(props.bookingId)
    detail.value = data
    prepDraft.value = data.notes.prep_md
    recapDraft.value = data.notes.recap_md
  } catch (err) {
    error.value = err?.response?.data?.detail ?? 'Failed to load meeting.'
  } finally {
    loading.value = false
  }
}

async function savePrep(val) {
  await meetingsAPI.patchNotes(props.bookingId, { prep_md: val })
  emit('changed')
}
async function saveRecap(val) {
  await meetingsAPI.patchNotes(props.bookingId, { recap_md: val })
  emit('changed')
}

async function addTask() {
  const title = (newTask.value || '').trim()
  if (!title) return
  const { data } = await meetingsAPI.createTask(props.bookingId, { title })
  detail.value.tasks.push(data)
  newTask.value = ''
  emit('changed')
}
async function toggleTask(t, done) {
  const { data } = await meetingsAPI.updateTask(props.bookingId, t.id, { done })
  Object.assign(t, data)
  emit('changed')
}
async function renameTask(t, title) {
  const { data } = await meetingsAPI.updateTask(props.bookingId, t.id, { title })
  Object.assign(t, data)
}
async function deleteTask(t) {
  await meetingsAPI.deleteTask(props.bookingId, t.id)
  detail.value.tasks = detail.value.tasks.filter(x => x.id !== t.id)
  emit('changed')
}

async function redraft(force) {
  const { data } = await meetingsAPI.aiDraft(props.bookingId, force)
  detail.value.notes = { ...detail.value.notes, ...data, ai_skipped: data.ai_skipped ?? null }
  prepDraft.value = data.prep_md
}

async function markHeld() { /* status patch — wire in v1.1 */ }
async function markNoShow() { /* status patch — wire in v1.1 */ }

function fmt(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}
function relPast(iso) {
  if (!iso) return ''
  const diff = (Date.now() - new Date(iso).getTime()) / 86400000
  if (diff < 7) return `${Math.round(diff)}d ago`
  return `${Math.round(diff / 7)}w ago`
}
</script>
