<!--
  Markdown — renders markdown text as styled HTML, sanitized.
  Used for AI-generated content (strategy memo, assistant replies, briefing notes).
  Styled to match the dashboard's Control Room Minimalism palette.
-->
<template>
  <div class="markdown text-sm text-ctrl-text leading-relaxed" v-html="html" />
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps({
  source: { type: String, default: '' },
})

marked.setOptions({
  gfm: true,
  breaks: true,
})

const html = computed(() => {
  if (!props.source) return ''
  const raw = marked.parse(props.source)
  return DOMPurify.sanitize(raw, { USE_PROFILES: { html: true } })
})
</script>

<style scoped>
.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  font-family: var(--font-display, 'Syne', sans-serif);
  font-weight: 600;
  color: theme('colors.ctrl.text');
  letter-spacing: -0.01em;
  line-height: 1.25;
}
.markdown :deep(h1) { font-size: 1.125rem; margin: 1.25rem 0 0.5rem; }
.markdown :deep(h2) { font-size: 1rem;     margin: 1.25rem 0 0.5rem; }
.markdown :deep(h3) { font-size: 0.875rem; margin: 1rem 0 0.375rem;
                       text-transform: uppercase; letter-spacing: 0.06em;
                       color: theme('colors.ctrl.muted'); font-weight: 500; }
.markdown :deep(h4) { font-size: 0.8125rem; margin: 0.875rem 0 0.25rem; }

.markdown :deep(p) { margin: 0 0 0.75rem; }
.markdown :deep(p:last-child) { margin-bottom: 0; }

.markdown :deep(strong) { color: theme('colors.ctrl.text'); font-weight: 600; }
.markdown :deep(em)     { color: theme('colors.ctrl.muted'); font-style: italic; }

.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 0 0 0.75rem;
  padding-left: 1.25rem;
}
.markdown :deep(li) { margin: 0.25rem 0; }
.markdown :deep(li::marker) { color: theme('colors.ctrl.dim'); }

.markdown :deep(hr) {
  border: 0;
  border-top: 1px solid theme('colors.ctrl.border');
  margin: 1.25rem 0;
}

.markdown :deep(a) {
  color: theme('colors.status.info');
  text-decoration: none;
  border-bottom: 1px dashed currentColor;
}
.markdown :deep(a:hover) { opacity: 0.85; }

.markdown :deep(code) {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 0.8125em;
  background: theme('colors.ctrl.raised');
  border: 1px solid theme('colors.ctrl.border');
  padding: 0.05rem 0.35rem;
  border-radius: 3px;
  color: theme('colors.ctrl.text');
}
.markdown :deep(pre) {
  background: theme('colors.ctrl.raised');
  border: 1px solid theme('colors.ctrl.border');
  border-radius: 4px;
  padding: 0.75rem;
  overflow-x: auto;
  margin: 0 0 0.75rem;
}
.markdown :deep(pre code) {
  background: transparent;
  border: 0;
  padding: 0;
}

.markdown :deep(blockquote) {
  margin: 0 0 0.75rem;
  padding-left: 0.75rem;
  border-left: 2px solid theme('colors.status.info');
  color: theme('colors.ctrl.muted');
  font-style: italic;
}

.markdown :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 0.75rem;
  font-size: 0.8125rem;
}
.markdown :deep(th),
.markdown :deep(td) {
  border-bottom: 1px solid theme('colors.ctrl.border');
  padding: 0.45rem 0.6rem;
  text-align: left;
}
.markdown :deep(th) {
  color: theme('colors.ctrl.muted');
  font-weight: 500;
  text-transform: uppercase;
  font-size: 0.6875rem;
  letter-spacing: 0.06em;
}
</style>
