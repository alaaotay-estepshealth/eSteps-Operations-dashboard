<template>
  <div class="min-h-screen flex items-center justify-center bg-ctrl-bg">
    <div class="absolute inset-0 opacity-[0.025]"
         style="background-image: linear-gradient(oklch(92% 0.004 245) 1px, transparent 1px), linear-gradient(90deg, oklch(92% 0.004 245) 1px, transparent 1px); background-size: 32px 32px;" />

    <div class="relative w-full max-w-xs">
      <div class="mb-8">
        <div class="font-display font-bold text-2xl tracking-wide text-ctrl-text">eSteps</div>
        <div class="text-2xs text-ctrl-muted uppercase tracking-label mt-1">Operations Dashboard</div>
      </div>

      <div class="bg-ctrl-panel border border-ctrl-border rounded-md p-7 shadow-float">
        <form class="space-y-5" @submit.prevent="submit">
          <div>
            <label class="font-display text-2xs uppercase tracking-label text-ctrl-muted block mb-2">
              Username
            </label>
            <input
              v-model.trim="username"
              type="text"
              class="w-full bg-ctrl-surface border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-2.5 placeholder-ctrl-dim transition-colors focus:border-status-info focus:outline-none"
              placeholder="admin"
              autocomplete="username"
              required
            />
          </div>

          <div>
            <label class="font-display text-2xs uppercase tracking-label text-ctrl-muted block mb-2">
              Password
            </label>
            <input
              v-model="password"
              type="password"
              class="w-full bg-ctrl-surface border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-2.5 placeholder-ctrl-dim transition-colors focus:border-status-info focus:outline-none"
              placeholder="••••••••"
              autocomplete="current-password"
              required
            />
          </div>

          <div v-if="error" class="flex items-start gap-2 bg-status-err-bg border border-status-err rounded px-3 py-2">
            <AlertCircle class="w-3.5 h-3.5 text-status-err flex-shrink-0 mt-0.5" />
            <p class="text-xs text-status-err">{{ error }}</p>
          </div>

          <button
            type="submit"
            :disabled="loading"
            class="w-full bg-status-info text-ctrl-bg font-display font-semibold text-xs uppercase tracking-label py-2.5 rounded transition-all hover:opacity-90 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed mt-2"
          >
            <span v-if="loading" class="flex items-center justify-center gap-2">
              <div class="w-3.5 h-3.5 border border-ctrl-bg border-t-transparent rounded-full animate-spin" />
              Authenticating
            </span>
            <span v-else>Sign In</span>
          </button>
        </form>
      </div>

      <p class="text-center text-2xs text-ctrl-dim mt-5">Demo: admin / admin123</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { AlertCircle } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth.js'

const router   = useRouter()
const auth     = useAuthStore()
const username = ref('')
const password = ref('')
const loading  = ref(false)
const error    = ref('')

async function submit() {
  error.value   = ''
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    router.push('/overview')
  } catch {
    error.value = 'Invalid username or password.'
  } finally {
    loading.value = false
  }
}
</script>
