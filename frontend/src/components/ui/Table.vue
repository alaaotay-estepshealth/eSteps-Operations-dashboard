<template>
  <div class="overflow-x-auto">
    <table class="w-full text-sm border-collapse">
      <thead>
        <tr class="border-b border-ctrl-border">
          <th
            v-for="col in columns"
            :key="col.key ?? col"
            class="px-4 py-2.5 font-display font-semibold text-2xs uppercase tracking-label text-ctrl-muted whitespace-nowrap"
            :class="col.align === 'right' ? 'text-right' : 'text-left'"
          >
            {{ col.label ?? col }}
          </th>
        </tr>
      </thead>
      <tbody>
        <template v-if="loading">
          <tr v-for="n in skeletonRows" :key="`sk-${n}`" class="border-b border-ctrl-divide">
            <td v-for="col in columns" :key="col.key ?? col" class="px-4 py-3">
              <div class="h-3 rounded bg-ctrl-raised animate-pulse" :style="{ width: skeletonWidth() }" />
            </td>
          </tr>
        </template>

        <template v-else-if="rows.length > 0">
          <tr
            v-for="(row, idx) in rows"
            :key="idx"
            class="border-b border-ctrl-divide hover:bg-ctrl-panel transition-colors duration-100"
          >
            <td
              v-for="col in columns"
              :key="col.key ?? col"
              class="px-4 py-2.5 text-ctrl-text"
              :class="col.align === 'right' ? 'text-right tabnum' : ''"
            >
              <slot :name="`cell-${col.key ?? col}`" :row="row" :value="row[col.key ?? col]">
                {{ row[col.key ?? col] }}
              </slot>
            </td>
          </tr>
        </template>

        <tr v-else>
          <td :colspan="columns.length" class="px-4 py-10 text-center">
            <div class="flex flex-col items-center gap-2 text-ctrl-muted">
              <component :is="emptyIcon" class="w-7 h-7 opacity-30" />
              <span class="text-xs">{{ emptyMessage }}</span>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { Inbox } from 'lucide-vue-next'

defineProps({
  columns:      { type: Array,   required: true },
  rows:         { type: Array,   default: () => [] },
  loading:      { type: Boolean, default: false },
  skeletonRows: { type: Number,  default: 5 },
  emptyMessage: { type: String,  default: 'No data available' },
  emptyIcon:    { default: () => Inbox },
})

function skeletonWidth() {
  const widths = ['35%', '50%', '65%', '42%', '58%', '75%']
  return widths[Math.floor(Math.random() * widths.length)]
}
</script>
