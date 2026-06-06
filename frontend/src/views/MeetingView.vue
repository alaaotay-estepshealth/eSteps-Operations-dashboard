<template>
  <div class="space-y-4 max-w-5xl">
    <button @click="$router.back()" class="text-2xs text-ctrl-muted hover:text-ctrl-text">← Back</button>
    <MeetingDrawer :open="true" :booking-id="bookingId" @close="$router.back()" />
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'
import MeetingDrawer from '../components/MeetingDrawer.vue'

const route = useRoute()
const bookingId = route.params.bookingId
</script>
