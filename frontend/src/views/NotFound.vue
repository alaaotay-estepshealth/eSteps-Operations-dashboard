<template>
  <div class="min-h-full flex items-center justify-center py-24">
    <div class="max-w-md w-full text-center space-y-6 px-6">
      <img
        src="/logo_inversed.png"
        alt="eSteps"
        class="h-14 w-auto mx-auto object-contain opacity-70"
        draggable="false"
      />
      <div class="space-y-2">
        <div class="font-display text-2xs uppercase tracking-label text-ctrl-dim">
          404 · route not found
        </div>
        <h1 class="font-display font-bold text-2xl text-ctrl-text leading-tight">
          Nothing here
        </h1>
        <p class="text-sm text-ctrl-muted">
          This URL was moved, renamed, or never existed. The sidebar has all live views.
        </p>
      </div>
      <div class="pt-2">
        <RouterLink
          to="/briefing"
          class="inline-flex items-center gap-2 px-4 py-2 rounded border border-status-info/40 text-status-info hover:bg-status-info-bg transition-all text-sm"
        >
          Back to Briefing
        </RouterLink>
      </div>
    </div>
  </div>
</template>

<script setup>
// RouterLink is auto-registered by vue-router — no import needed.
</script>
