<!--
  PromptDialog — styled drop-in replacement for window.prompt().

  Usage:
    <PromptDialog v-model="open"
      title="New folder"
      label="Folder name"
      placeholder="e.g. q3-launch"
      :default-value="''"
      @submit="handleSubmit" />
-->
<template>
  <Teleport to="body">
    <transition name="pd-fade">
      <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-[2px]" @click.self="cancel">
        <div class="bg-ctrl-surface border border-ctrl-border rounded-lg shadow-2xl w-full max-w-md mx-4 overflow-hidden">
          <form @submit.prevent="submit">
            <div class="flex items-start justify-between gap-3 px-5 pt-5">
              <div>
                <div class="font-display font-semibold text-base text-ctrl-text leading-tight">{{ title }}</div>
                <p v-if="message" class="text-xs text-ctrl-muted mt-1 leading-relaxed">{{ message }}</p>
              </div>
              <button type="button" @click="cancel" class="text-ctrl-dim hover:text-ctrl-text text-lg leading-none -mt-1">✕</button>
            </div>
            <div class="px-5 pt-4">
              <label v-if="label" class="block text-2xs uppercase tracking-label text-ctrl-dim mb-1">{{ label }}</label>
              <input
                ref="inputEl"
                v-model="value"
                :type="inputType"
                :placeholder="placeholder"
                :minlength="minlength || undefined"
                class="w-full bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-2 focus:outline-none focus:border-status-info placeholder-ctrl-dim"
              />
              <p v-if="hint" class="text-2xs text-ctrl-dim mt-1.5">{{ hint }}</p>
            </div>
            <div class="flex items-center justify-end gap-2 px-5 py-4 mt-3 bg-ctrl-panel/40 border-t border-ctrl-border">
              <button
                type="button"
                @click="cancel"
                class="px-3 py-1.5 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text hover:border-ctrl-text transition-all"
              >{{ cancelLabel }}</button>
              <button
                type="submit"
                :disabled="!canSubmit"
                class="px-3 py-1.5 text-xs bg-status-info-bg text-status-info border border-status-info rounded hover:opacity-85 disabled:opacity-40 transition-all"
              >{{ submitLabel }}</button>
            </div>
          </form>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  modelValue:   { type: Boolean, default: false },
  title:        { type: String, default: 'Enter value' },
  message:      { type: String, default: '' },
  label:        { type: String, default: '' },
  placeholder:  { type: String, default: '' },
  defaultValue: { type: String, default: '' },
  hint:         { type: String, default: '' },
  inputType:    { type: String, default: 'text' },
  minlength:    { type: Number, default: 1 },
  submitLabel:  { type: String, default: 'Save' },
  cancelLabel:  { type: String, default: 'Cancel' },
})
const emit = defineEmits(['update:modelValue', 'submit', 'cancel'])

const visible = ref(props.modelValue)
const value   = ref(props.defaultValue)
const inputEl = ref(null)

watch(() => props.modelValue, (v) => {
  visible.value = v
  if (v) {
    value.value = props.defaultValue
    nextTick(() => inputEl.value?.focus())
  }
})
watch(visible, (v) => emit('update:modelValue', v))

const canSubmit = computed(() => value.value.trim().length >= (props.minlength || 1))

function submit() {
  if (!canSubmit.value) return
  const v = value.value.trim()
  visible.value = false
  emit('submit', v)
}
function cancel() { visible.value = false; emit('cancel') }
</script>

<style scoped>
.pd-fade-enter-active, .pd-fade-leave-active { transition: opacity 0.12s ease-out; }
.pd-fade-enter-from, .pd-fade-leave-to { opacity: 0; }
</style>
