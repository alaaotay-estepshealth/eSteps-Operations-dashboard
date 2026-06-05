<!--
  GTMTreeNode — one recursive node of the GTM strategy file explorer.
  The row is a <div role="button"> (NOT a real button) so we can render
  an actual <button> for "delete" inside it — nested buttons are invalid
  HTML and Brave/Chrome silently strip the inner one, killing the click.
-->
<template>
  <div :class="depth === 0 ? '' : 'pl-3'">
    <div
      role="button"
      tabindex="0"
      @click="onClick"
      @keydown.enter.prevent="onClick"
      @keydown.space.prevent="onClick"
      :title="node.path"
      class="group w-full flex items-center gap-1.5 px-1.5 py-1 rounded text-xs text-left transition-colors duration-100 cursor-pointer select-none"
      :class="active ? 'bg-ctrl-panel text-ctrl-text' : 'text-ctrl-muted hover:text-ctrl-text hover:bg-ctrl-panel'"
    >
      <ChevronRight
        v-if="node.type === 'folder'"
        class="w-3.5 h-3.5 flex-shrink-0 transition-transform duration-100"
        :class="open ? 'rotate-90 text-ctrl-text' : 'text-ctrl-dim'"
      />
      <component
        :is="iconFor(node)"
        class="w-3.5 h-3.5 flex-shrink-0"
        :class="node.type === 'folder' ? 'text-status-warn' : 'text-ctrl-dim'"
      />
      <span class="truncate flex-1">{{ node.name }}</span>
      <span v-if="node.type === 'file' && node.size_bytes" class="text-2xs text-ctrl-dim tabnum">{{ fmtSize(node.size_bytes) }}</span>
      <button
        v-if="canDelete && depth > 0"
        type="button"
        @click.stop="$emit('delete', node.path)"
        @keydown.enter.stop
        @keydown.space.stop
        class="opacity-0 group-hover:opacity-100 focus:opacity-100 text-ctrl-dim hover:text-status-err transition-opacity p-0.5"
        title="Delete"
        aria-label="Delete"
      >
        <Trash2 class="w-3 h-3" />
      </button>
    </div>

    <div v-if="node.type === 'folder' && open && node.children?.length" class="mt-0.5 border-l border-ctrl-border ml-2">
      <GTMTreeNode
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :selected-path="selectedPath"
        :can-delete="canDelete"
        :depth="depth + 1"
        @select="$emit('select', $event)"
        @delete="$emit('delete', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ChevronRight, Folder, FolderOpen, FileText, FileSpreadsheet, FileImage, File as FileIcon, Trash2 } from 'lucide-vue-next'

const props = defineProps({
  node:         { type: Object, required: true },
  selectedPath: { type: String, default: '' },
  canDelete:    { type: Boolean, default: false },
  depth:        { type: Number, default: 0 },
})
const emit = defineEmits(['select', 'delete'])

const open = ref(props.depth === 0)  // roots open by default
const active = computed(() => props.selectedPath === props.node.path)

function onClick() {
  if (props.node.type === 'folder') {
    open.value = !open.value
  } else {
    emit('select', props.node.path)
  }
}

function iconFor(n) {
  if (n.type === 'folder') return open.value ? FolderOpen : Folder
  const ext = (n.name || '').toLowerCase().split('.').pop()
  if (['md', 'txt', 'rst', 'log'].includes(ext)) return FileText
  if (['csv', 'xls', 'xlsx', 'json', 'yaml', 'yml'].includes(ext)) return FileSpreadsheet
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext)) return FileImage
  return FileIcon
}

function fmtSize(b) {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}
</script>
