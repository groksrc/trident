<script setup lang="ts">
import { WifiOff, RefreshCw } from 'lucide-vue-next'
import { useUIStore } from '~/stores/ui'

const ui = useUIStore()
</script>

<template>
  <Transition name="banner">
    <div
      v-if="!ui.isConnected && ui.isReconnecting"
      class="fixed left-0 right-0 top-14 z-40 flex items-center justify-center gap-2 bg-yellow-100 px-4 py-2 text-sm text-yellow-800"
    >
      <RefreshCw class="h-4 w-4 animate-spin" />
      <span>Reconnecting...</span>
    </div>
    <div
      v-else-if="!ui.isConnected"
      class="fixed left-0 right-0 top-14 z-40 flex items-center justify-center gap-2 bg-red-100 px-4 py-2 text-sm text-red-800"
    >
      <WifiOff class="h-4 w-4" />
      <span>Disconnected from server</span>
    </div>
  </Transition>
</template>

<style scoped>
.banner-enter-active,
.banner-leave-active {
  transition: all 0.3s ease;
}
.banner-enter-from,
.banner-leave-to {
  opacity: 0;
  transform: translateY(-100%);
}
</style>
