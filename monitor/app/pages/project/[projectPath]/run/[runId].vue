<script setup lang="ts">
import { useProjectsStore } from '~/stores/projects'
import { useRunsStore, type WorkflowNode } from '~/stores/runs'
import { useUIStore } from '~/stores/ui'

// Lazy load DAG visualization to avoid importing Vue Flow on server
const LazyDAGVisualization = defineAsyncComponent(() =>
  import('~/components/dag/DAGVisualization.vue')
)

const projects = useProjectsStore()
const runs = useRunsStore()
const ui = useUIStore()
const { decodePath } = useProjectPath()

const route = useRoute()

// Decode project path from URL
const projectPath = computed(() => {
  const encoded = route.params.projectPath as string
  if (!encoded) return null
  try {
    return decodePath(encoded)
  } catch {
    return null
  }
})

const runId = computed(() => route.params.runId as string)

// Use useAsyncData for SSR-friendly data loading
const { pending } = useAsyncData(
  `run-${runId.value}`,
  async () => {
    const path = projectPath.value
    const rid = runId.value
    if (!path || !rid) return null

    // Load project if not loaded
    if (path !== projects.projectPath) {
      try {
        await projects.setProject(path)
        if (projects.projectPath) {
          await runs.fetchRuns(projects.projectPath)
        }
      } catch (error) {
        ui.showError('Failed to load project')
        navigateTo('/')
        return null
      }
    }

    // Select the run
    if (rid !== runs.currentRunId) {
      await runs.selectRun(rid)
    }

    return { loaded: true }
  },
  {
    watch: [projectPath, runId],
  }
)

// Computed display values
const runStatus = computed(() => runs.currentRun?.status || 'unknown')
const runStarted = computed(() => {
  if (!runs.currentRun?.started_at) return ''
  return new Date(runs.currentRun.started_at).toLocaleString()
})
const runDuration = computed(() => {
  if (!runs.currentRun?.started_at) return ''
  const start = new Date(runs.currentRun.started_at)
  const end = runs.currentRun.ended_at ? new Date(runs.currentRun.ended_at) : new Date()
  const ms = end.getTime() - start.getTime()
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`
})

const statusColor = computed(() => {
  switch (runStatus.value) {
    case 'completed': return runs.currentRun?.success ? 'text-green-600' : 'text-red-600'
    case 'running': return 'text-blue-600'
    case 'failed': return 'text-red-600'
    case 'interrupted': return 'text-yellow-600'
    default: return 'text-gray-600'
  }
})

// Handle node click from DAG
function handleNodeClick(node: WorkflowNode) {
  ui.selectNode(node.id)
}

// Check if we have workflow data
const hasWorkflowData = computed(() => {
  return runs.workflowData?.nodes && runs.workflowData.nodes.length > 0
})

const isLoading = computed(() => pending.value || (!hasWorkflowData.value && runs.currentRunId))
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- Run header -->
    <div class="border-b bg-card px-4 py-3">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="font-mono text-sm">{{ runId?.slice(0, 8) }}...</h1>
          <div class="mt-1 flex items-center gap-4 text-xs text-muted-foreground">
            <span :class="statusColor" class="capitalize font-medium">{{ runStatus }}</span>
            <span v-if="runStarted">Started: {{ runStarted }}</span>
            <span v-if="runDuration">Duration: {{ runDuration }}</span>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <!-- Future: Replay button will go here -->
        </div>
      </div>
    </div>

    <!-- DAG visualization -->
    <div class="flex-1 overflow-hidden">
      <!-- Loading state -->
      <div v-if="isLoading" class="h-full flex items-center justify-center bg-muted/20">
        <div class="text-center p-8">
          <div class="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto" />
          <p class="mt-4 text-sm text-muted-foreground">Loading workflow...</p>
        </div>
      </div>

      <!-- DAG component (lazy loaded to avoid Vue Flow on server) -->
      <ClientOnly v-else-if="hasWorkflowData">
        <Suspense>
          <LazyDAGVisualization
            :nodes="runs.workflowData!.nodes"
            :edges="runs.workflowData!.edges"
            :selected-node-id="ui.selectedNodeId"
            @node-click="handleNodeClick"
          />
          <template #fallback>
            <div class="h-full flex items-center justify-center bg-muted/20">
              <div class="text-center p-8">
                <div class="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto" />
                <p class="mt-4 text-sm text-muted-foreground">Loading visualization...</p>
              </div>
            </div>
          </template>
        </Suspense>
        <template #fallback>
          <div class="h-full flex items-center justify-center bg-muted/20">
            <div class="text-center p-8">
              <div class="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto" />
              <p class="mt-4 text-sm text-muted-foreground">Initializing...</p>
            </div>
          </div>
        </template>
      </ClientOnly>

      <!-- No data state -->
      <div v-else class="h-full flex items-center justify-center bg-muted/20">
        <div class="text-center p-8">
          <p class="text-sm text-muted-foreground">No workflow data available</p>
        </div>
      </div>
    </div>
  </div>
</template>
