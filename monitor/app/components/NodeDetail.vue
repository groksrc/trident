<script setup lang="ts">
import { CheckCircle, XCircle, Circle, Loader2, SkipForward, Clock, Cpu, ArrowRight, AlertTriangle, Play, FileText } from 'lucide-vue-next'
import { useTimeAgo } from '@vueuse/core'
import { useProjectsStore } from '~/stores/projects'
import { useRunsStore } from '~/stores/runs'
import { useUIStore } from '~/stores/ui'

interface NodeData {
  id: string
  type: string
  label: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  startTime: string | null
  endTime: string | null
  duration: number | null
  input: Record<string, unknown> | null
  output: Record<string, unknown> | null
  error: string | null
  model: string | null
  tokens: { input?: number; output?: number }
}

interface PromptData {
  nodeId: string
  name?: string
  description?: string
  promptTemplate: string
  frontmatter: Record<string, unknown>
  filePath: string
}

const props = defineProps<{
  node: NodeData
}>()

const emit = defineEmits<{
  replay: [nodeId: string, newRunId: string]
}>()

const projects = useProjectsStore()
const runs = useRunsStore()
const ui = useUIStore()
const { navigateToRun } = useProjectPath()

// Prompt fetching
const promptData = ref<PromptData | null>(null)
const promptLoading = ref(false)
const promptError = ref<string | null>(null)
const isReplaying = ref(false)

// Check if this node type can have a prompt (step nodes have prompts)
const canHavePrompt = computed(() => {
  return props.node.type === 'step' || props.node.type === 'prompt'
})

// Fetch prompt when node changes
watch(() => props.node.id, async () => {
  promptData.value = null
  promptError.value = null

  if (!canHavePrompt.value || !projects.projectPath) return

  promptLoading.value = true
  try {
    const data = await $fetch<PromptData>(`/api/workflow/prompt/${props.node.id}`, {
      query: { project: projects.projectPath },
    })
    promptData.value = data
  } catch (err: any) {
    // 404 is expected for nodes without prompts
    if (err.statusCode !== 404) {
      promptError.value = err.message || 'Failed to load prompt'
    }
  } finally {
    promptLoading.value = false
  }
}, { immediate: true })

// Replay from this node
async function replayFromHere() {
  if (!projects.projectPath || !runs.currentRunId) return

  isReplaying.value = true
  try {
    const response = await $fetch<{ newRunId: string; status: string; message?: string }>(
      '/api/runs/replay',
      {
        method: 'POST',
        body: {
          projectPath: projects.projectPath,
          runId: runs.currentRunId,
          startFrom: props.node.id,
        },
      }
    )

    if (response.status === 'started') {
      ui.showSuccess(`Replay started from ${props.node.label}`)
      emit('replay', props.node.id, response.newRunId)

      // Refresh runs list and navigate
      await runs.fetchRuns(projects.projectPath)
      await runs.selectRun(response.newRunId)
      navigateToRun(projects.projectPath, response.newRunId)
    }
  } catch (err: any) {
    ui.showError(err.data?.message || err.message || 'Failed to start replay')
  } finally {
    isReplaying.value = false
  }
}

const statusIcon = computed(() => {
  switch (props.node.status) {
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
  switch (props.node.status) {
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

const statusLabel = computed(() => {
  switch (props.node.status) {
    case 'completed':
      return 'Completed'
    case 'failed':
      return 'Failed'
    case 'running':
      return 'Running'
    case 'skipped':
      return 'Skipped'
    default:
      return 'Pending'
  }
})

const startTimeAgo = computed(() => {
  if (!props.node.startTime) return null
  return useTimeAgo(new Date(props.node.startTime)).value
})

const formatDuration = (ms: number | null) => {
  if (!ms) return null
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`
  return `${Math.floor(ms / 60000)}m ${((ms % 60000) / 1000).toFixed(0)}s`
}

const formatJSON = (obj: unknown) => {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

const activeTab = ref<'input' | 'output' | 'error' | 'prompt'>('output')

watch(() => props.node.id, () => {
  // Reset to output tab when node changes, unless there's an error
  activeTab.value = props.node.error ? 'error' : 'output'
})

// Show prompt tab by default for step nodes if prompt exists
watch(promptData, (data) => {
  if (data && activeTab.value === 'output' && !props.node.output) {
    activeTab.value = 'prompt'
  }
})
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- Header -->
    <div class="border-b p-4">
      <div class="flex items-center gap-3">
        <div
          class="flex h-10 w-10 items-center justify-center rounded-lg"
          :class="{
            'bg-green-100 dark:bg-green-900/30': node.status === 'completed',
            'bg-red-100 dark:bg-red-900/30': node.status === 'failed',
            'bg-blue-100 dark:bg-blue-900/30': node.status === 'running',
            'bg-muted': node.status === 'pending' || node.status === 'skipped',
          }"
        >
          <component
            :is="statusIcon"
            class="h-5 w-5"
            :class="[statusColor, node.status === 'running' && 'animate-spin']"
          />
        </div>
        <div class="min-w-0 flex-1">
          <h3 class="font-semibold truncate">{{ node.label }}</h3>
          <p class="text-sm text-muted-foreground">{{ statusLabel }}</p>
        </div>
      </div>
    </div>

    <!-- Meta info -->
    <div class="border-b p-4 space-y-3">
      <!-- Type -->
      <div class="flex items-center gap-2 text-sm">
        <Cpu class="h-4 w-4 text-muted-foreground" />
        <span class="text-muted-foreground">Type:</span>
        <span class="font-medium">{{ node.type }}</span>
      </div>

      <!-- Model -->
      <div v-if="node.model" class="flex items-center gap-2 text-sm">
        <ArrowRight class="h-4 w-4 text-muted-foreground" />
        <span class="text-muted-foreground">Model:</span>
        <span class="font-medium truncate">{{ node.model }}</span>
      </div>

      <!-- Timing -->
      <div v-if="node.startTime" class="flex items-center gap-2 text-sm">
        <Clock class="h-4 w-4 text-muted-foreground" />
        <span class="text-muted-foreground">Started:</span>
        <span class="font-medium">{{ startTimeAgo }}</span>
      </div>

      <!-- Duration -->
      <div v-if="node.duration" class="flex items-center gap-2 text-sm">
        <Clock class="h-4 w-4 text-muted-foreground" />
        <span class="text-muted-foreground">Duration:</span>
        <span class="font-medium tabular-nums">{{ formatDuration(node.duration) }}</span>
      </div>

      <!-- Tokens -->
      <div v-if="node.tokens?.input || node.tokens?.output" class="flex items-center gap-2 text-sm">
        <ArrowRight class="h-4 w-4 text-muted-foreground" />
        <span class="text-muted-foreground">Tokens:</span>
        <span class="font-medium tabular-nums">
          <span v-if="node.tokens.input">{{ node.tokens.input.toLocaleString() }} in</span>
          <span v-if="node.tokens.input && node.tokens.output"> / </span>
          <span v-if="node.tokens.output">{{ node.tokens.output.toLocaleString() }} out</span>
        </span>
      </div>
    </div>

    <!-- Replay Button -->
    <div v-if="node.status === 'completed' || node.status === 'failed'" class="border-b p-3">
      <Button
        variant="outline"
        size="sm"
        class="w-full"
        :disabled="isReplaying"
        @click="replayFromHere"
      >
        <Loader2 v-if="isReplaying" class="mr-2 h-4 w-4 animate-spin" />
        <Play v-else class="mr-2 h-4 w-4" />
        {{ isReplaying ? 'Starting...' : 'Replay from here' }}
      </Button>
    </div>

    <!-- Tabs -->
    <div class="flex border-b">
      <button
        v-if="promptData"
        class="flex-1 px-4 py-2 text-sm font-medium transition-colors"
        :class="activeTab === 'prompt' ? 'border-b-2 border-primary text-primary' : 'text-muted-foreground hover:text-foreground'"
        @click="activeTab = 'prompt'"
      >
        <span class="flex items-center justify-center gap-1">
          <FileText class="h-3 w-3" />
          Prompt
        </span>
      </button>
      <button
        v-if="node.input"
        class="flex-1 px-4 py-2 text-sm font-medium transition-colors"
        :class="activeTab === 'input' ? 'border-b-2 border-primary text-primary' : 'text-muted-foreground hover:text-foreground'"
        @click="activeTab = 'input'"
      >
        Input
      </button>
      <button
        v-if="node.output"
        class="flex-1 px-4 py-2 text-sm font-medium transition-colors"
        :class="activeTab === 'output' ? 'border-b-2 border-primary text-primary' : 'text-muted-foreground hover:text-foreground'"
        @click="activeTab = 'output'"
      >
        Output
      </button>
      <button
        v-if="node.error"
        class="flex-1 px-4 py-2 text-sm font-medium transition-colors"
        :class="activeTab === 'error' ? 'border-b-2 border-red-500 text-red-500' : 'text-muted-foreground hover:text-foreground'"
        @click="activeTab = 'error'"
      >
        <span class="flex items-center justify-center gap-1">
          <AlertTriangle class="h-3 w-3" />
          Error
        </span>
      </button>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-auto p-4">
      <!-- Prompt -->
      <div v-if="activeTab === 'prompt'">
        <div v-if="promptLoading" class="flex items-center justify-center py-8">
          <Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
        <div v-else-if="promptData">
          <!-- Prompt metadata -->
          <div v-if="promptData.name || promptData.description" class="mb-3">
            <h4 v-if="promptData.name" class="font-medium text-sm">{{ promptData.name }}</h4>
            <p v-if="promptData.description" class="text-xs text-muted-foreground mt-1">{{ promptData.description }}</p>
          </div>
          <!-- Prompt template -->
          <div class="relative">
            <div class="absolute top-2 right-2 text-xs text-muted-foreground bg-background/80 px-2 py-0.5 rounded">
              {{ promptData.filePath.split('/').pop() }}
            </div>
            <pre class="text-xs bg-muted p-3 rounded-lg overflow-auto whitespace-pre-wrap break-all font-mono">{{ promptData.promptTemplate }}</pre>
          </div>
          <p class="mt-2 text-xs text-muted-foreground">
            Variables like <code class="bg-muted px-1 rounded">{<!-- -->{variable}}</code> are replaced with input values at runtime.
          </p>
        </div>
        <div v-else-if="promptError" class="text-center text-red-500 py-8">
          {{ promptError }}
        </div>
        <div v-else class="text-center text-muted-foreground py-8">
          No prompt template for this node
        </div>
      </div>

      <!-- Input -->
      <div v-if="activeTab === 'input' && node.input">
        <pre class="text-xs bg-muted p-3 rounded-lg overflow-auto whitespace-pre-wrap break-all">{{ formatJSON(node.input) }}</pre>
      </div>

      <!-- Output -->
      <div v-if="activeTab === 'output' && node.output">
        <pre class="text-xs bg-muted p-3 rounded-lg overflow-auto whitespace-pre-wrap break-all">{{ formatJSON(node.output) }}</pre>
      </div>

      <!-- Error -->
      <div v-if="activeTab === 'error' && node.error">
        <div class="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg p-3">
          <pre class="text-xs text-red-700 dark:text-red-300 whitespace-pre-wrap break-all">{{ node.error }}</pre>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="!node.input && !node.output && !node.error" class="text-center text-muted-foreground py-8">
        <p>No data available</p>
        <p v-if="node.status === 'pending'" class="text-sm mt-1">Node hasn't executed yet</p>
      </div>
    </div>
  </div>
</template>
