<template>
  <div class="space-y-6 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>
    <div v-if="notice" class="flex items-center gap-3 bg-status-ok-bg border border-status-ok rounded px-4 py-3 text-status-ok text-xs">
      <CheckCircle class="w-4 h-4 flex-shrink-0" />
      {{ notice }}
    </div>

    <StatRow :stats="[
      { label: 'Total Users', value: users.length },
      { label: 'Admins',      value: countByRole('admin'),    status: 'ok' },
      { label: 'Operators',   value: countByRole('operator'), status: 'info' },
      { label: 'Read-only',   value: countByRole('readonly'),  sub: 'monitor + audit' },
    ]" />

    <SectionContainer title="Users" subtitle="Create, edit, deactivate or delete dashboard accounts">
      <template #action>
        <button
          @click="resetForm(); showForm = true"
          class="px-3 py-1.5 text-xs bg-status-info-bg text-status-info border border-status-info rounded hover:opacity-80 transition-all inline-flex items-center gap-1.5"
        >
          <UserPlus class="w-3.5 h-3.5" /> New user
        </button>
      </template>

      <Table
        :columns="columns"
        :rows="users"
        :loading="loading"
        :skeleton-rows="6"
        empty-message="No users yet"
        :empty-icon="Users"
      >
        <template #cell-username="{ row }">
          <div class="flex items-center gap-2">
            <span class="font-medium text-ctrl-text">{{ row.username }}</span>
            <Badge v-if="me && row.id === me.id" variant="info">you</Badge>
          </div>
        </template>
        <template #cell-email="{ value }"><span class="text-ctrl-muted text-xs">{{ value || '—' }}</span></template>
        <template #cell-role="{ row }">
          <select
            :value="row.role"
            @change="onRoleChange(row, $event.target.value)"
            :disabled="row.id === me?.id"
            class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1 focus:outline-none disabled:opacity-50"
          >
            <option value="admin">admin</option>
            <option value="operator">operator</option>
            <option value="readonly">readonly</option>
          </select>
        </template>
        <template #cell-is_active="{ row }">
          <button
            @click="toggleActive(row)"
            :disabled="row.id === me?.id"
            class="px-2 py-0.5 text-2xs rounded border tabnum transition-all disabled:opacity-40"
            :class="row.is_active
              ? 'bg-status-ok-bg text-status-ok border-status-ok'
              : 'bg-status-err-bg text-status-err border-status-err'"
          >
            {{ row.is_active ? 'active' : 'disabled' }}
          </button>
        </template>
        <template #cell-created_at="{ value }">
          <span class="tabnum text-ctrl-dim text-xs">{{ fmtDate(value) }}</span>
        </template>
        <template #cell-actions="{ row }">
          <div class="flex items-center gap-1.5">
            <button
              @click="openReset(row)"
              class="px-2 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-info hover:border-status-info transition-all inline-flex items-center gap-1"
              title="Reset password"
            >
              <KeyRound class="w-3 h-3" /> Password
            </button>
            <button
              @click="onDelete(row)"
              :disabled="row.id === me?.id"
              class="px-2 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-err hover:border-status-err disabled:opacity-30 transition-all inline-flex items-center gap-1"
              title="Delete user"
            >
              <Trash2 class="w-3 h-3" /> Delete
            </button>
          </div>
        </template>
      </Table>
    </SectionContainer>

    <!-- Create modal -->
    <div v-if="showForm" class="fixed inset-0 z-40 flex items-center justify-center bg-black/60" @click.self="showForm = false">
      <div class="bg-ctrl-surface border border-ctrl-border rounded-lg shadow-xl w-full max-w-md p-6 space-y-4">
        <div class="flex items-start justify-between">
          <div>
            <div class="font-display font-semibold text-lg text-ctrl-text">New user</div>
            <div class="text-2xs text-ctrl-muted uppercase tracking-label">Create dashboard account</div>
          </div>
          <button @click="showForm = false" class="text-ctrl-dim hover:text-ctrl-text text-lg leading-none">✕</button>
        </div>

        <form @submit.prevent="onCreate" class="space-y-3">
          <div>
            <label class="block text-2xs uppercase tracking-label text-ctrl-dim mb-1">Username</label>
            <input v-model="form.username" type="text" required minlength="3" maxlength="64"
              placeholder="e.g. j.smith"
              class="w-full bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-2 focus:outline-none placeholder-ctrl-dim" />
          </div>
          <div>
            <label class="block text-2xs uppercase tracking-label text-ctrl-dim mb-1">Email</label>
            <input v-model="form.email" type="email" required maxlength="255"
              placeholder="j.smith@estepshealth.com"
              class="w-full bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-2 focus:outline-none placeholder-ctrl-dim" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-2xs uppercase tracking-label text-ctrl-dim mb-1">Password</label>
              <input v-model="form.password" type="password" required minlength="8"
                class="w-full bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-2 focus:outline-none" />
            </div>
            <div>
              <label class="block text-2xs uppercase tracking-label text-ctrl-dim mb-1">Role</label>
              <select v-model="form.role" class="w-full bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-2 focus:outline-none">
                <option value="readonly">readonly — monitor only</option>
                <option value="operator">operator — pipeline actions</option>
                <option value="admin">admin — full access</option>
              </select>
            </div>
          </div>
          <div class="flex items-center justify-end gap-2 pt-2">
            <button type="button" @click="showForm = false"
              class="px-3 py-1.5 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text">
              Cancel
            </button>
            <button type="submit" :disabled="saving"
              class="px-3 py-1.5 text-xs bg-status-info-bg text-status-info border border-status-info rounded hover:opacity-80 disabled:opacity-40 transition-all">
              {{ saving ? 'Creating…' : 'Create user' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Password reset modal -->
    <div v-if="resetTarget" class="fixed inset-0 z-40 flex items-center justify-center bg-black/60" @click.self="resetTarget = null">
      <div class="bg-ctrl-surface border border-ctrl-border rounded-lg shadow-xl w-full max-w-sm p-6 space-y-4">
        <div class="font-display font-semibold text-base text-ctrl-text">Reset password — {{ resetTarget.username }}</div>
        <input v-model="resetPassword" type="password" minlength="8" placeholder="New password (min 8 chars)"
          class="w-full bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-2 focus:outline-none placeholder-ctrl-dim" />
        <div class="flex items-center justify-end gap-2">
          <button @click="resetTarget = null" class="px-3 py-1.5 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text">Cancel</button>
          <button @click="confirmReset" :disabled="saving || resetPassword.length < 8"
            class="px-3 py-1.5 text-xs bg-status-warn-bg text-status-warn border border-status-warn rounded hover:opacity-80 disabled:opacity-40 transition-all">
            Update password
          </button>
        </div>
      </div>
    </div>

    <ConfirmDialog
      v-model="confirmOpen"
      :title="confirmTitle"
      :message="confirmMessage"
      :detail="confirmDetail"
      confirm-label="Delete user"
      variant="danger"
      @confirm="confirmDelete"
    />

  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { AlertCircle, CheckCircle, KeyRound, Trash2, UserPlus, Users } from 'lucide-vue-next'
import { usersAPI } from '../api/index.js'
import Badge from '../components/ui/Badge.vue'
import ConfirmDialog from '../components/ui/ConfirmDialog.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'

const confirmOpen    = ref(false)
const pendingDelete  = ref(null)
const confirmTitle   = ref('')
const confirmMessage = ref('')
const confirmDetail  = ref('')

const users  = ref([])
const me     = ref(null)
const loading = ref(false)
const saving  = ref(false)
const error   = ref('')
const notice  = ref('')

const showForm = ref(false)
const form = ref({ username: '', email: '', password: '', role: 'readonly' })

const resetTarget   = ref(null)
const resetPassword = ref('')

const columns = [
  { key: 'username',   label: 'User' },
  { key: 'email',      label: 'Email' },
  { key: 'role',       label: 'Role' },
  { key: 'is_active',  label: 'Status' },
  { key: 'created_at', label: 'Created' },
  { key: 'actions',    label: '' },
]

const countByRole = (r) => computed(() => users.value.filter(u => u.role === r).length).value

function fmtDate(v) {
  if (!v) return '—'
  return new Date(v).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function flash(msg) { notice.value = msg; setTimeout(() => notice.value = '', 3000) }
function resetForm() { form.value = { username: '', email: '', password: '', role: 'readonly' } }

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [list, self] = await Promise.all([usersAPI.list(), usersAPI.me()])
    users.value = list.data
    me.value = self.data
  } catch (err) {
    error.value = err?.response?.data?.detail ?? 'Failed to load users.'
  } finally {
    loading.value = false
  }
}

async function onCreate() {
  saving.value = true
  error.value = ''
  try {
    await usersAPI.create(form.value)
    showForm.value = false
    flash(`User ${form.value.username} created.`)
    await load()
  } catch (err) {
    error.value = err?.response?.data?.detail ?? 'Failed to create user.'
  } finally {
    saving.value = false
  }
}

async function onRoleChange(row, newRole) {
  if (newRole === row.role) return
  try {
    await usersAPI.update(row.id, { role: newRole })
    flash(`${row.username} → ${newRole}`)
    await load()
  } catch (err) {
    error.value = err?.response?.data?.detail ?? 'Failed to change role.'
    await load()
  }
}

async function toggleActive(row) {
  try {
    await usersAPI.update(row.id, { is_active: !row.is_active })
    flash(`${row.username} ${row.is_active ? 'deactivated' : 'activated'}.`)
    await load()
  } catch (err) {
    error.value = err?.response?.data?.detail ?? 'Failed to change status.'
  }
}

function openReset(row) {
  resetTarget.value = row
  resetPassword.value = ''
}

async function confirmReset() {
  if (!resetTarget.value || resetPassword.value.length < 8) return
  saving.value = true
  try {
    await usersAPI.update(resetTarget.value.id, { password: resetPassword.value })
    flash(`Password reset for ${resetTarget.value.username}.`)
    resetTarget.value = null
    resetPassword.value = ''
  } catch (err) {
    error.value = err?.response?.data?.detail ?? 'Failed to reset password.'
  } finally {
    saving.value = false
  }
}

function onDelete(row) {
  pendingDelete.value  = row
  confirmTitle.value   = `Delete ${row.username}`
  confirmMessage.value = 'This account will be removed and the user will no longer be able to sign in. This cannot be undone.'
  confirmDetail.value  = `${row.username} · ${row.role} · ${row.email || '—'}`
  confirmOpen.value    = true
}

async function confirmDelete() {
  const row = pendingDelete.value
  if (!row) return
  try {
    await usersAPI.remove(row.id)
    flash(`${row.username} deleted.`)
    await load()
  } catch (err) {
    error.value = err?.response?.data?.detail ?? 'Failed to delete user.'
  } finally {
    pendingDelete.value = null
  }
}

onMounted(load)
</script>
