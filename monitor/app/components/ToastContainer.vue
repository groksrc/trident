<script setup lang="ts">
import { X, Info, CheckCircle, AlertTriangle, XCircle } from 'lucide-vue-next'
import { useUIStore } from '~/stores/ui'

const ui = useUIStore()

const iconMap = {
  info: Info,
  success: CheckCircle,
  warning: AlertTriangle,
  error: XCircle,
}

const colorMap = {
  info: 'border-blue-200 bg-blue-50 text-blue-800',
  success: 'border-green-200 bg-green-50 text-green-800',
  warning: 'border-yellow-200 bg-yellow-50 text-yellow-800',
  error: 'border-red-200 bg-red-50 text-red-800',
}
</script>

<template>
  <div class="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
    <TransitionGroup name="toast">
      <div
        v-for="toast in ui.toasts"
        :key="toast.id"
        class="flex items-start gap-2 rounded-lg border p-3 shadow-lg"
        :class="colorMap[toast.type]"
      >
        <component :is="iconMap[toast.type]" class="h-5 w-5 shrink-0" />
        <span class="flex-1 text-sm">{{ toast.message }}</span>
        <button
          class="shrink-0 opacity-60 hover:opacity-100"
          @click="ui.removeToast(toast.id)"
        >
          <X class="h-4 w-4" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active {
  transition: all 0.3s ease;
}
.toast-leave-active {
  transition: all 0.2s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
</style>
