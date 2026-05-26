<template>
  <section>
    <div class="section-rule mb-5">
      <h2 class="font-display font-semibold text-xs uppercase tracking-label text-ctrl-text whitespace-nowrap">
        {{ title }}
      </h2>
      <span v-if="subtitle" class="text-2xs text-ctrl-muted whitespace-nowrap -ml-2">{{ subtitle }}</span>
    </div>
    <div v-if="$slots.action" class="flex justify-end -mt-3 mb-4">
      <slot name="action" />
    </div>
    <slot />
  </section>
</template>

<script setup>
defineProps({
  title:    { type: String, required: true },
  subtitle: { type: String, default: '' },
})
</script>
