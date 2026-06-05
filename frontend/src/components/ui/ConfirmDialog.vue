<!--
  ConfirmDialog — styled drop-in replacement for window.confirm().

  Usage:
    const ok = await confirmDialog.open({ title, message, confirmLabel, variant: 'danger'|'warn'|'info' })
    if (ok) { ... }

  Or with v-model:
    <ConfirmDialog v-model="open" :title="..." :message="..." @confirm="doIt" />
-->
<template>
  <Teleport to="body">
    <transition name="cd-fade">
      <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-[2px]" @click.self="cancel">
        <div class="bg-ctrl-surface border border-ctrl-border rounded-lg shadow-2xl w-full max-w-md mx-4 overflow-hidden">
          <div class="flex items-start gap-3 px-5 pt-5">
            <div :class="iconWrap" class="flex-shrink-0 w-9 h-9 rounded-full border flex items-center justify-center">
              <component :is="icon" class="w-4 h-4" />
            </div>
            <div class="flex-1 pt-0.5">
              <div class="font-display font-semibold text-base text-ctrl-text leading-tight">{{ title }}</div>
              <p v-if="message" class="text-xs text-ctrl-muted mt-1.5 leading-relaxed">{{ message }}</p>
              <p v-if="detail" class="text-2xs text-ctrl-dim mt-2 font-mono break-all bg-ctrl-panel border border-ctrl-border rounded px-2 py-1">{{ detail }}</p>
            </div>
            <button @click="cancel" class="text-ctrl-dim hover:text-ctrl-text text-lg leading-none -mt-1">✕</button>
          </div>
          <div class="flex items-center justify-end gap-2 px-5 py-4 mt-3 bg-ctrl-panel/40 border-t border-ctrl-border">
            <button
              @click="cancel"
              class="px-3 py-1.5 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text hover:border-ctrl-text transition-all"
            >{{ cancelLabel }}</button>
            <button
              ref="confirmBtn"
              @click="confirm"
              :class="confirmClass"
              class="px-3 py-1.5 text-xs rounded border transition-all"
            >{{ confirmLabel }}</button>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { AlertTriangle, AlertCircle, Info, CheckCircle } from 'lucide-vue-next'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title:        { type: String, default: 'Confirm' },
  message:      { type: String, default: '' },
  detail:       { type: String, default: '' },
  confirmLabel: { type: String, default: 'Confirm' },
  cancelLabel:  { type: String, default: 'Cancel' },
  variant:      { type: String, default: 'info' }, // danger | warn | info | ok
})
const emit = defineEmits(['update:modelValue', 'confirm', 'cancel'])

const visible    = ref(props.modelValue)
const confirmBtn = ref(null)

watch(() => props.modelValue, (v) => {
  visible.value = v
  if (v) nextTick(() => confirmBtn.value?.focus())
})
watch(visible, (v) => emit('update:modelValue', v))

const icon = computed(() => ({
  danger: AlertCircle, warn: AlertTriangle, ok: CheckCircle, info: Info,
}[props.variant] || Info))
const iconWrap = computed(() => ({
  danger: 'bg-status-err-bg text-status-err border-status-err',
  warn:   'bg-status-warn-bg text-status-warn border-status-warn',
  ok:     'bg-status-ok-bg text-status-ok border-status-ok',
  info:   'bg-status-info-bg text-status-info border-status-info',
}[props.variant] || 'bg-status-info-bg text-status-info border-status-info'))
const confirmClass = computed(() => ({
  danger: 'bg-status-err-bg text-status-err border-status-err hover:opacity-85',
  warn:   'bg-status-warn-bg text-status-warn border-status-warn hover:opacity-85',
  ok:     'bg-status-ok-bg text-status-ok border-status-ok hover:opacity-85',
  info:   'bg-status-info-bg text-status-info border-status-info hover:opacity-85',
}[props.variant] || 'bg-status-info-bg text-status-info border-status-info hover:opacity-85'))

function confirm() { visible.value = false; emit('confirm') }
function cancel()  { visible.value = false; emit('cancel') }
</script>

<style scoped>
.cd-fade-enter-active, .cd-fade-leave-active { transition: opacity 0.12s ease-out; }
.cd-fade-enter-from, .cd-fade-leave-to { opacity: 0; }
</style>
