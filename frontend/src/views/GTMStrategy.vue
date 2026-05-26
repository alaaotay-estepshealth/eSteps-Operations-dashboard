<template>
  <div class="space-y-8 max-w-screen-xl">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <StatRow :stats="[
      { label: 'Products',    value: 3,                sub: 'eSteps Health · Robosan · Taxini' },
      { label: 'Strategy Docs', value: strategies.length, sub: 'markdown files' },
      { label: 'Directories', value: directories.length },
    ]" />

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-8">
      <!-- File tree -->
      <SectionContainer title="Strategy Documents" subtitle="Click to view content" class="xl:col-span-1">
        <div v-if="loading" class="space-y-2">
          <div v-for="i in 8" :key="i" class="h-6 bg-ctrl-raised rounded animate-pulse" />
        </div>
        <div v-else-if="!strategies.length">
          <EmptyState :icon="FolderOpen" message="No strategy files found" />
        </div>
        <div v-else class="space-y-1 max-h-[600px] overflow-y-auto">
          <template v-for="dir in directories" :key="dir">
            <div class="text-2xs font-display font-medium uppercase tracking-label text-ctrl-dim px-2 pt-3 pb-1">{{ dir }}</div>
            <button
              v-for="file in strategiesByDir(dir)"
              :key="file.path"
              @click="selectFile(file)"
              class="w-full text-left px-3 py-1.5 rounded text-xs transition-all duration-100"
              :class="selectedFile?.path === file.path
                ? 'bg-ctrl-panel text-ctrl-text'
                : 'text-ctrl-muted hover:text-ctrl-text hover:bg-ctrl-panel'"
            >
              {{ file.name }}
            </button>
          </template>
        </div>
      </SectionContainer>

      <!-- Document viewer -->
      <SectionContainer :title="selectedFile?.name ?? 'Select a document'" :subtitle="selectedFile?.directory ?? ''" class="xl:col-span-2">
        <div v-if="contentLoading" class="space-y-3">
          <div v-for="i in 10" :key="i" class="h-4 bg-ctrl-raised rounded animate-pulse" :style="{ width: `${40 + Math.random() * 50}%` }" />
        </div>
        <div v-else-if="!selectedFile">
          <EmptyState :icon="FileText" message="Select a strategy document from the tree" />
        </div>
        <div v-else class="prose prose-invert prose-sm max-w-none text-ctrl-text leading-relaxed">
          <div v-html="renderedContent" />
        </div>
      </SectionContainer>
    </div>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, FileText, FolderOpen } from 'lucide-vue-next'
import { gtmAPI } from '../api/index.js'
import EmptyState from '../components/ui/EmptyState.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'

const strategies     = ref([])
const selectedFile   = ref(null)
const content        = ref('')
const loading        = ref(false)
const contentLoading = ref(false)
const error          = ref('')

const directories = computed(() => {
  const dirs = [...new Set(strategies.value.map((s) => s.directory))]
  return dirs.sort()
})

function strategiesByDir(dir) {
  return strategies.value.filter((s) => s.directory === dir)
}

const renderedContent = computed(() => {
  if (!content.value) return ''
  return content.value
    .replace(/^### (.+)$/gm, '<h3 class="text-sm font-display font-semibold text-ctrl-text mt-6 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-base font-display font-semibold text-ctrl-text mt-8 mb-3">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-lg font-display font-bold text-ctrl-text mt-8 mb-4">$1</h1>')
    .replace(/^\- (.+)$/gm, '<li class="ml-4 text-ctrl-muted">$1</li>')
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 text-ctrl-muted list-decimal">$1</li>')
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-ctrl-text">$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code class="bg-ctrl-raised px-1 py-0.5 rounded text-2xs font-mono">$1</code>')
    .replace(/\n\n/g, '<br/><br/>')
    .replace(/\n/g, '<br/>')
})

async function selectFile(file) {
  selectedFile.value = file
  contentLoading.value = true
  try {
    const { data } = await gtmAPI.getStrategy(file.path)
    content.value = data.content ?? data
  } catch {
    content.value = 'Failed to load file content.'
  } finally {
    contentLoading.value = false
  }
}

async function load() {
  loading.value = true
  error.value   = ''
  try {
    const { data } = await gtmAPI.listStrategies()
    strategies.value = Array.isArray(data) ? data : (data.strategies ?? [])
  } catch {
    error.value = 'Failed to load strategy files.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
