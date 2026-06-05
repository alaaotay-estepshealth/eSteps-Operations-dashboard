<template>
  <div class="space-y-8 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>
    <div v-if="notice" class="flex items-center gap-3 bg-status-ok-bg border border-status-ok rounded px-4 py-3 text-status-ok text-xs">
      <CheckCircle class="w-4 h-4 flex-shrink-0" />
      {{ notice }}
    </div>

    <StatRow :stats="[
      { label: 'Products',     value: 3,                sub: 'eSteps Health  briefings' },
      { label: 'Documents', value: fileCount,       sub: 'in this archive' },
      { label: 'Meetings',       value: folderCount },
    ]" />

    <!-- Magazine-style layout: tree floats left; viewer flows around it AND
         reclaims full width once the tree column ends below. -->
    <SectionContainer :title="selectedNode?.name ?? 'Meet Prep'" :subtitle="selectedNode?.path ?? 'Per-meeting folders and supporting files'">
      <template #action v-if="selectedNode">
        <a
          :href="downloadHref"
          target="_blank"
          class="px-2.5 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text hover:border-ctrl-text transition-all inline-flex items-center gap-1.5"
        >
          <Download class="w-3 h-3" /> Download
        </a>
      </template>

      <div class="gtm-flow">
        <!-- Floated tree column (top-left). Viewer text wraps to its right and below. -->
        <aside class="gtm-tree-col bg-ctrl-panel/60 border border-ctrl-border rounded p-3">
          <div class="flex items-center justify-between gap-2 mb-2">
            <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted">Meeting Materials</div>
            <div v-if="canWrite" class="flex items-center gap-1">
              <button
                @click="triggerFileUpload"
                :disabled="uploading"
                class="p-1 rounded border border-ctrl-border text-ctrl-muted hover:text-ctrl-text hover:border-ctrl-text disabled:opacity-40 transition-all"
                title="Upload files"
              >
                <Upload class="w-3 h-3" />
              </button>
              <button
                @click="triggerFolderUpload"
                :disabled="uploading"
                class="p-1 rounded border border-ctrl-border text-ctrl-muted hover:text-ctrl-text hover:border-ctrl-text disabled:opacity-40 transition-all"
                title="Upload a folder"
              >
                <FolderPlus class="w-3 h-3" />
              </button>
              <button
                @click="newFolder"
                :disabled="uploading"
                class="p-1 rounded border border-ctrl-border text-ctrl-muted hover:text-ctrl-text hover:border-ctrl-text disabled:opacity-40 transition-all"
                title="Create empty folder"
              >
                <Plus class="w-3 h-3" />
              </button>
            </div>
          </div>

          <!-- hidden file inputs -->
          <input ref="fileInput"   type="file" multiple class="hidden" @change="onFilesPicked" />
          <input ref="folderInput" type="file" multiple webkitdirectory directory class="hidden" @change="onFilesPicked" />

          <div
            v-if="canWrite"
            @dragenter.prevent="dragOver = true"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
            class="mb-2 border border-dashed rounded px-2 py-1.5 text-2xs transition-all text-center"
            :class="dragOver ? 'border-status-info text-status-info bg-status-info-bg' : 'border-ctrl-border text-ctrl-dim'"
          >
            <span v-if="uploading">Uploading {{ uploadProgress }}%…</span>
            <span v-else-if="dragOver">Drop to upload</span>
            <span v-else>Drag files here</span>
          </div>

          <div v-if="loading" class="space-y-2">
            <div v-for="i in 6" :key="i" class="h-5 bg-ctrl-raised rounded animate-pulse" />
          </div>
          <div v-else-if="!tree.length">
            <EmptyState :icon="FolderOpen" message="No meet-prep root configured" />
          </div>
          <div v-else class="space-y-0.5 max-h-[calc(100vh-340px)] overflow-y-auto pr-1">
            <GTMTreeNode
              v-for="root in tree"
              :key="root.path"
              :node="root"
              :selected-path="selectedPath"
              :can-delete="canWrite"
              @select="selectFile"
              @delete="onDelete"
            />
          </div>
        </aside>

        <!-- Viewer flows around the floated tree. -->
        <div class="gtm-viewer">
          <div v-if="contentLoading" class="space-y-3">
            <div v-for="i in 10" :key="i" class="h-4 bg-ctrl-raised rounded animate-pulse" :style="{ width: `${40 + Math.random() * 50}%` }" />
          </div>
          <div v-else-if="!selectedNode">
            <EmptyState :icon="FileText" message="Select a meet-prep document from the tree" />
          </div>
          <div v-else-if="ext(selectedNode.name) === 'pdf'" class="border border-ctrl-border rounded overflow-hidden bg-ctrl-panel/30">
            <div class="flex items-center justify-between gap-3 px-3 py-2 border-b border-ctrl-border bg-ctrl-panel/60">
              <div class="flex items-center gap-2 min-w-0">
                <FileText class="w-3.5 h-3.5 text-ctrl-muted flex-shrink-0" />
                <span class="font-display text-2xs uppercase tracking-label text-ctrl-muted truncate">{{ selectedNode.name }}</span>
                <span v-if="pdfLoading" class="text-2xs text-ctrl-dim flex-shrink-0">Loading…</span>
              </div>
              <div class="flex items-center gap-1.5 flex-shrink-0">
                <button
                  @click="openPdfNewTab"
                  :disabled="!pdfBlobUrl"
                  class="px-2.5 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text hover:border-ctrl-text disabled:opacity-30 transition-all inline-flex items-center gap-1.5"
                  title="Open PDF in a new browser tab"
                >
                  <ExternalLink class="w-3 h-3" /> New tab
                </button>
                <a
                  :href="downloadHref"
                  target="_blank"
                  class="px-2.5 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text hover:border-ctrl-text transition-all inline-flex items-center gap-1.5"
                >
                  <Download class="w-3 h-3" /> Download
                </a>
              </div>
            </div>
            <div class="relative bg-ctrl-bg">
              <div v-if="pdfLoading && !pdfBlobUrl" class="h-[60vh] flex items-center justify-center text-xs text-ctrl-muted">
                Loading PDF preview…
              </div>
              <iframe
                v-else-if="pdfBlobUrl"
                :src="pdfSrc"
                class="w-full h-[78vh] block"
                :title="selectedNode.name"
                frameborder="0"
              />
              <div v-else-if="pdfError" class="p-4 text-xs text-status-err">{{ pdfError }}</div>
            </div>
          </div>
          <div v-else-if="!selectedNode.is_text" class="text-xs text-ctrl-muted">
            <p class="mb-3">Inline preview is not available for <code class="bg-ctrl-raised px-1.5 py-0.5 rounded text-2xs">{{ ext(selectedNode.name) }}</code> files.</p>
            <a :href="downloadHref" target="_blank" class="inline-flex items-center gap-1.5 text-status-info hover:underline">
              <Download class="w-3.5 h-3.5" /> Download {{ selectedNode.name }}
            </a>
          </div>
          <Markdown v-else :source="content" />
        </div>

        <div class="clear-both" />
      </div>
    </SectionContainer>

    <PromptDialog
      v-model="folderPromptOpen"
      title="New folder"
      :label="`Inside ${folderParentLabel || 'Meet Prep'}`"
      placeholder="e.g. mayo-clinic-2026-06"
      hint="You can nest with /  →  e.g. dr-elder/brief"
      submit-label="Create folder"
      @submit="onFolderName"
    />
    <ConfirmDialog
      v-model="confirmOpen"
      :title="confirmCfg.title"
      :message="confirmCfg.message"
      :detail="confirmCfg.detail"
      :confirm-label="confirmCfg.confirmLabel"
      variant="danger"
      @confirm="confirmCfg.onYes && confirmCfg.onYes()"
    />

  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, CheckCircle, Download, ExternalLink, FileText, FolderOpen, FolderPlus, Plus, Upload } from 'lucide-vue-next'
import { meetsAPI } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import ConfirmDialog from '../components/ui/ConfirmDialog.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import Markdown from '../components/ui/Markdown.vue'
import PromptDialog from '../components/ui/PromptDialog.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import GTMTreeNode from '../components/GTMTreeNode.vue'

const folderPromptOpen = ref(false)
const folderParentLabel = ref('')
const confirmOpen = ref(false)
const confirmCfg  = ref({ title: '', message: '', detail: '', confirmLabel: 'Delete', onYes: null })

const auth = useAuthStore()
const canWrite = computed(() => auth.isOperator)
const isAdmin  = computed(() => auth.isAdmin)

const tree         = ref([])
const selectedNode = ref(null)
const selectedPath = ref('')
const content      = ref('')
const loading      = ref(false)
const contentLoading = ref(false)
const error        = ref('')
const notice       = ref('')

// PDF inline preview: fetch with auth header → blob → object URL → iframe.
// (The download endpoint requires a JWT, so a plain <iframe src=...> won't work.)
const pdfBlobUrl = ref('')
const pdfLoading = ref(false)
const pdfError   = ref('')
let _pdfBlobUrl  = ''
// `#toolbar=0&navpanes=0&view=FitH` hides Chromium's default PDF chrome so the
// embed visually matches the dashboard. Our own header bar above provides the
// open-in-tab / download actions.
const pdfSrc = computed(() => pdfBlobUrl.value ? `${pdfBlobUrl.value}#toolbar=0&navpanes=0&view=FitH` : '')

function _revokePdf() {
  if (_pdfBlobUrl) { URL.revokeObjectURL(_pdfBlobUrl); _pdfBlobUrl = '' }
  pdfBlobUrl.value = ''
}

async function _loadPdf(path) {
  _revokePdf()
  pdfError.value = ''
  pdfLoading.value = true
  try {
    const blob = await meetsAPI.fetchBlob(path, 'application/pdf')
    _pdfBlobUrl = URL.createObjectURL(blob)
    pdfBlobUrl.value = _pdfBlobUrl
  } catch (err) {
    pdfError.value = err?.response?.data?.detail ?? 'Failed to load PDF.'
  } finally {
    pdfLoading.value = false
  }
}

watch(selectedNode, (node) => {
  if (!node || node.type !== 'file') { _revokePdf(); return }
  const e = (node.name || '').toLowerCase().split('.').pop()
  if (e === 'pdf') _loadPdf(node.path)
  else _revokePdf()
})

onBeforeUnmount(_revokePdf)

function openPdfNewTab() {
  if (pdfBlobUrl.value) window.open(pdfBlobUrl.value, '_blank', 'noopener')
}
const uploading    = ref(false)
const uploadProgress = ref(0)
const dragOver     = ref(false)

const fileInput   = ref(null)
const folderInput = ref(null)

const fileCount = computed(() => countNodes(tree.value, n => n.type === 'file'))
const folderCount = computed(() => countNodes(tree.value, n => n.type === 'folder') - tree.value.length)
const downloadHref = computed(() => selectedNode.value ? meetsAPI.downloadUrl(selectedNode.value.path) : '#')

function countNodes(nodes, pred) {
  let n = 0
  for (const x of nodes) {
    if (pred(x)) n++
    if (x.children?.length) n += countNodes(x.children, pred)
  }
  return n
}

function ext(name) { return (name || '').split('.').pop()?.toLowerCase() }

function flash(msg) {
  notice.value = msg
  setTimeout(() => { notice.value = '' }, 3000)
}

function findNode(nodes, path) {
  for (const n of nodes) {
    if (n.path === path) return n
    if (n.children?.length) {
      const hit = findNode(n.children, path)
      if (hit) return hit
    }
  }
  return null
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await meetsAPI.getTree()
    tree.value = Array.isArray(data) ? data : []
    if (selectedPath.value) {
      const refreshed = findNode(tree.value, selectedPath.value)
      if (!refreshed) {
        selectedNode.value = null
        selectedPath.value = ''
        content.value = ''
      } else {
        selectedNode.value = refreshed
      }
    }
  } catch {
    error.value = 'Failed to load strategy tree.'
  } finally {
    loading.value = false
  }
}

async function selectFile(path) {
  const node = findNode(tree.value, path)
  if (!node) return
  selectedNode.value = node
  selectedPath.value = path
  if (!node.is_text) { content.value = ''; return }
  contentLoading.value = true
  try {
    const { data } = await meetsAPI.getStrategy(path)
    content.value = data.content ?? ''
  } catch {
    content.value = 'Failed to load file content.'
  } finally {
    contentLoading.value = false
  }
}

function triggerFileUpload()   { fileInput.value?.click() }
function triggerFolderUpload() { folderInput.value?.click() }

async function onFilesPicked(e) {
  const files = [...(e.target.files || [])]
  e.target.value = ''
  if (files.length) await doUpload(files)
}

async function onDrop(e) {
  dragOver.value = false
  const files = [...(e.dataTransfer.files || [])]
  if (files.length) await doUpload(files)
}

async function doUpload(files) {
  if (!canWrite.value) return
  uploading.value = true
  uploadProgress.value = 0
  error.value = ''
  try {
    const fd = new FormData()
    const folder = targetFolderPath()
    fd.append('folder', folder)
    for (const f of files) {
      fd.append('files', f)
      fd.append('paths', f.webkitRelativePath || '')
    }
    const { data } = await meetsAPI.upload(fd, (p) => {
      if (p.total) uploadProgress.value = Math.round((p.loaded / p.total) * 100)
    })
    flash(`Uploaded ${data.uploaded.length}${data.skipped.length ? ` · skipped ${data.skipped.length}` : ''}.`)
    await load()
  } catch (err) {
    error.value = err?.response?.data?.detail ?? 'Upload failed.'
  } finally {
    uploading.value = false
    uploadProgress.value = 0
  }
}

function targetFolderPath() {
  // Where uploads + new folders should land. Includes the root prefix.
  // Selected folder → itself. Selected file → its parent. Nothing → first root.
  if (selectedNode.value) {
    if (selectedNode.value.type === 'folder') return selectedNode.value.path
    return selectedNode.value.path.split('/').slice(0, -1).join('/')
  }
  return tree.value[0]?.path || ''
}

function newFolder() {
  if (!canWrite.value) return
  const parent = targetFolderPath()
  if (!parent) {
    error.value = 'No strategy root configured.'
    return
  }
  folderParentLabel.value = parent
  folderPromptOpen.value = true
}

async function onFolderName(name) {
  const parent = targetFolderPath()
  if (!parent || !name) return
  try {
    await meetsAPI.createFolder(`${parent}/${name}`)
    flash('Folder created.')
    await load()
  } catch (err) {
    error.value = err?.response?.data?.detail ?? 'Folder creation failed.'
  }
}

function onDelete(path) {
  if (!canWrite.value) return
  const node = findNode(tree.value, path)
  const isFolder = node?.type === 'folder'
  confirmCfg.value = {
    title: isFolder ? 'Delete folder' : 'Delete file',
    message: isFolder
      ? 'This deletes the folder and every file inside it. This cannot be undone.'
      : 'This file will be permanently removed.',
    detail: path,
    confirmLabel: 'Delete',
    onYes: async () => {
      try {
        await meetsAPI.remove(path)
        flash('Deleted.')
        if (selectedPath.value === path || selectedPath.value.startsWith(path + '/')) {
          selectedPath.value = ''
          selectedNode.value = null
          content.value = ''
        }
        await load()
      } catch (err) {
        error.value = err?.response?.data?.detail ?? 'Delete failed.'
      }
    },
  }
  confirmOpen.value = true
}

useStaleFetch(load)
</script>

<style scoped>
/* Stacked layout: folders section on top, viewer below at full width. */
.gtm-flow { display: flex; flex-direction: column; gap: 1.25rem; }
.gtm-tree-col { width: 100%; max-width: 36rem; }
.gtm-viewer { min-width: 0; }
</style>

