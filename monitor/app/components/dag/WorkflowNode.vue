<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import { CheckCircle, XCircle, Circle, Loader2, SkipForward, Cpu, FileInput, FileOutput } from 'lucide-vue-next'

interface NodeData {
  label: string
  type: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  duration: number | null
  model: string | null
  tokens: { input?: number; output?: number }
}

const props = defineProps<{
  data: NodeData
  selected: boolean
}>()

const statusIcon = computed(() => {
  switch (props.data.status) {
    case 'completed':
      return CheckCircle
    case 'failed':
      return XCircle
    case 'running':
      return Loader2
    case 'skipped':
      return SkipForward
    default:
      return Circle
  }
})

const statusColor = computed(() => {
  switch (props.data.status) {
    case 'completed':
      return 'text-green-500'
    case 'failed':
      return 'text-red-500'
    case 'running':
      return 'text-blue-500'
    case 'skipped':
      return 'text-gray-400'
    default:
      return 'text-gray-300'
  }
})

const borderColor = computed(() => {
  if (props.selected) return 'border-primary ring-2 ring-primary/20'
  switch (props.data.status) {
    case 'completed':
      return 'border-green-500/50'
    case 'failed':
      return 'border-red-500/50'
    case 'running':
      return 'border-blue-500 animate-pulse'
    default:
      return 'border-border'
  }
})

const bgColor = computed(() => {
  switch (props.data.status) {
    case 'completed':
      return 'bg-green-50 dark:bg-green-950/30'
    case 'failed':
      return 'bg-red-50 dark:bg-red-950/30'
    case 'running':
      return 'bg-blue-50 dark:bg-blue-950/30'
    default:
      return 'bg-card'
  }
})

const nodeIcon = computed(() => {
  switch (props.data.type) {
    case 'input':
      return FileInput
    case 'output':
      return FileOutput
    default:
      return Cpu
  }
})

const formatDuration = (ms: number | null) => {
  if (!ms || ms < 0) return null // Hide negative durations (cached nodes)
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}
</script>

<template>
  <div
    class="min-w-[140px] rounded-lg border-2 shadow-sm transition-all"
    :class="[borderColor, bgColor]"
  >
    <!-- Target handle (top) -->
    <Handle
      type="target"
      :position="Position.Top"
      class="!bg-muted-foreground !border-background !w-3 !h-3"
    />

    <!-- Node content -->
    <div class="px-3 py-2">
      <div class="flex items-center gap-2">
        <component :is="nodeIcon" class="h-4 w-4 text-muted-foreground shrink-0" />
        <span class="font-medium text-sm truncate">{{ data.label }}</span>
        <component
          :is="statusIcon"
          class="h-4 w-4 shrink-0 ml-auto"
          :class="[statusColor, data.status === 'running' && 'animate-spin']"
        />
      </div>

      <!-- Meta info -->
      <div class="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
        <span v-if="data.type !== 'input' && data.type !== 'output'" class="truncate">
          {{ data.type }}
        </span>
        <span v-if="data.duration" class="ml-auto tabular-nums">
          {{ formatDuration(data.duration) }}
        </span>
      </div>

      <!-- Token usage -->
      <div v-if="data.tokens?.input || data.tokens?.output" class="mt-1 text-[10px] text-muted-foreground">
        <span v-if="data.tokens.input">{{ data.tokens.input }} in</span>
        <span v-if="data.tokens.input && data.tokens.output"> / </span>
        <span v-if="data.tokens.output">{{ data.tokens.output }} out</span>
      </div>
    </div>

    <!-- Source handle (bottom) -->
    <Handle
      type="source"
      :position="Position.Bottom"
      class="!bg-muted-foreground !border-background !w-3 !h-3"
    />
  </div>
</template>
