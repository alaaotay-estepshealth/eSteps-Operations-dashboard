<template>
  <router-view v-if="isLoginPage" />
  <div v-else class="flex h-screen bg-ctrl-bg overflow-hidden">
    <Sidebar />
    <div class="flex-1 flex flex-col overflow-hidden min-w-0">
      <TopBar />
      <main class="flex-1 overflow-y-auto px-7 py-7">
        <AlertBanner />
        <router-view v-slot="{ Component }">
          <keep-alive :max="10">
            <component :is="Component" :key="route.path" />
          </keep-alive>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { adminAPI } from './api/index.js'
import Sidebar from './components/Sidebar.vue'
import TopBar from './components/TopBar.vue'
import AlertBanner from './components/AlertBanner.vue'

const route       = useRoute()
const isLoginPage = computed(() => route.path === '/login')

const SYNC_INTERVAL_MS = 15 * 60 * 1000
let syncTimer

onMounted(() => {
  syncTimer = setInterval(() => {
    const token = localStorage.getItem('token')
    if (token) adminAPI.syncN8n(200).catch(() => {})
  }, SYNC_INTERVAL_MS)
})

onBeforeUnmount(() => clearInterval(syncTimer))
</script>
