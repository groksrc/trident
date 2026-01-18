<script setup lang="ts">
import { CheckCircle, XCircle, Circle, Loader2, AlertCircle, Trash2 } from 'lucide-vue-next'
import type { RunEntry } from '~/stores/runs'
import { useTimeAgo } from '@vueuse/core'

const props = defineProps<{
  run: RunEntry
  selected: boolean
}>()

const emit = defineEmits<{
  select: []
  delete: []
}>()

const isHovered = ref(false)

function handleDelete(event: MouseEvent) {
  event.stopPropagation()
  emit('delete')
}

const timeAgo = useTimeAgo(() => new Date(props.run.started_at))

const statusIcon = computed(() => {
  switch (props.run.status) {
    case 'completed':
      return props.run.success ? CheckCircle : XCircle
    case 'running':
      return Loader2
    case 'failed':
      return XCircle
    case 'interrupted':
      return AlertCircle
    default:
      return Circle
  }
})

const statusColor = computed(() => {
  switch (props.run.status) {
    case 'completed':
      return props.run.success ? 'text-green-500' : 'text-red-500'
    case 'running':
      return 'text-blue-500'
    case 'failed':
      return 'text-red-500'
    case 'interrupted':
      return 'text-yellow-500'
    default:
      return 'text-gray-400'
  }
})

const statusBg = computed(() => {
  if (!props.selected) return ''
  switch (props.run.status) {
    case 'completed':
      return props.run.success ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'
    case 'running':
      return 'bg-blue-50 border-blue-200'
    case 'failed':
      return 'bg-red-50 border-red-200'
    case 'interrupted':
      return 'bg-yellow-50 border-yellow-200'
    default:
      return 'bg-accent'
  }
})

const truncatedId = computed(() => props.run.run_id.slice(0, 8))

const statusLabel = computed(() => {
  if (props.run.status === 'running') return 'Running'
  if (props.run.status === 'completed') return props.run.success ? 'Success' : 'Failed'
  if (props.run.status === 'failed') return 'Failed'
  if (props.run.status === 'interrupted') return 'Interrupted'
  return ''
})
</script>

<template>
  <div
    class="group flex w-full items-center gap-2 rounded-md border px-2 py-2 text-sm transition-all cursor-pointer"
    :class="[
      selected ? statusBg : 'border-transparent hover:bg-accent/50 hover:border-border',
    ]"
    @click="emit('select')"
  >
    <!-- Status indicator -->
    <div class="relative shrink-0">
      <component
        :is="statusIcon"
        class="h-4 w-4"
        :class="[
          statusColor,
          run.status === 'running' && 'animate-spin',
        ]"
      />
      <!-- Pulse animation for running -->
      <span
        v-if="run.status === 'running'"
        class="absolute inset-0 rounded-full bg-blue-500 animate-ping opacity-30"
      />
    </div>

    <!-- Run info -->
    <div class="flex-1 min-w-0 text-left">
      <div class="flex items-center gap-1.5">
        <span class="font-mono text-xs truncate">{{ truncatedId }}</span>
        <span
          v-if="run.status === 'running'"
          class="shrink-0 text-[10px] font-medium text-blue-600 bg-blue-100 px-1 rounded"
        >
          LIVE
        </span>
      </div>
      <div class="flex items-center gap-2 mt-0.5">
        <span class="text-[11px] text-muted-foreground">{{ timeAgo }}</span>
        <span
          v-if="run.error_summary"
          class="text-[11px] text-red-500 truncate"
          :title="run.error_summary"
        >
          {{ run.error_summary.slice(0, 20) }}...
        </span>
      </div>
    </div>

    <!-- Delete button (visible on hover) -->
    <button
      class="shrink-0 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-100 hover:text-red-600 text-muted-foreground transition-all"
      title="Delete run"
      @click="handleDelete"
    >
      <Trash2 class="h-3.5 w-3.5" />
    </button>
  </div>
</template>
