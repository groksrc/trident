import { defineStore } from 'pinia'

export type RunStatus = 'running' | 'completed' | 'failed' | 'interrupted'
export type NodeState = 'pending' | 'running' | 'completed' | 'failed' | 'skipped'

export interface RunEntry {
  run_id: string
  project_name: string
  entrypoint: string | null
  status: RunStatus
  started_at: string
  ended_at: string | null
  success: boolean | null
  error_summary: string | null
}

export interface NodeTrace {
  id: string
  start_time: string | null
  end_time: string | null
  input: Record<string, unknown>
  output: Record<string, unknown> | null
  model: string | null
  tokens: { input: number; output: number } | null
  skipped: boolean
  error: string | null
  error_type: string | null
  cost_usd: number | null
  num_turns: number | null
}

export interface RunCheckpoint {
  run_id: string
  status: RunStatus
  completed_nodes: Record<string, { output: Record<string, unknown> }>
  pending_nodes: string[]
  total_cost_usd: number
}

export interface RunDetails {
  entry: RunEntry
  checkpoint: RunCheckpoint | null
  traces: Record<string, NodeTrace>
}

export interface WorkflowNode {
  id: string
  type: string
  label: string
  status: NodeState
  startTime: string | null
  endTime: string | null
  duration: number | null
  input: Record<string, unknown> | null
  output: Record<string, unknown> | null
  error: string | null
  model: string | null
  tokens: { input?: number; output?: number }
}

export interface WorkflowEdge {
  id: string
  source: string
  target: string
  mapping?: Record<string, string>
}

export interface WorkflowData {
  runId: string
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  startTime: string | null
  endTime: string | null
  error: string | null
}

interface RunsState {
  runs: RunEntry[]
  currentRunId: string | null
  currentRunDetails: RunDetails | null
  workflowData: WorkflowData | null
  isLoading: boolean
  error: string | null
}

export const useRunsStore = defineStore('runs', {
  state: (): RunsState => ({
    runs: [],
    currentRunId: null,
    currentRunDetails: null,
    workflowData: null,
    isLoading: false,
    error: null,
  }),

  getters: {
    currentRun: (state) => {
      if (!state.currentRunId) return null
      return state.runs.find(r => r.run_id === state.currentRunId) || null
    },

    runningRuns: (state) => state.runs.filter(r => r.status === 'running'),

    sortedRuns: (state) => {
      return [...state.runs].sort((a, b) => {
        return new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
      })
    },

    hasRuns: (state) => state.runs.length > 0,

    getNodeState: (state) => (nodeId: string): NodeState => {
      const details = state.currentRunDetails
      if (!details) return 'pending'

      const trace = details.traces[nodeId]
      if (!trace) return 'pending'

      if (trace.skipped) return 'skipped'
      if (trace.error) return 'failed'
      if (trace.end_time) return 'completed'
      if (trace.start_time) return 'running'
      return 'pending'
    },
  },

  actions: {
    async fetchRuns(projectPath: string) {
      this.isLoading = true
      this.error = null

      try {
        const response = await $fetch<{ runs: RunEntry[] }>('/api/runs', {
          query: { project: projectPath },
        })
        this.runs = response.runs
      } catch (error) {
        this.error = error instanceof Error ? error.message : 'Failed to fetch runs'
        this.runs = []
      } finally {
        this.isLoading = false
      }
    },

    async selectRun(runId: string) {
      this.currentRunId = runId
      await Promise.all([
        this.fetchRunDetails(runId),
        this.fetchWorkflowData(runId),
      ])
    },

    async fetchWorkflowData(runId: string) {
      const projectsStore = useProjectsStore()
      if (!projectsStore.projectPath) return

      try {
        const response = await $fetch<WorkflowData>(`/api/workflow/${runId}`, {
          query: { project: projectsStore.projectPath },
        })
        this.workflowData = response
      } catch (error) {
        console.error('Failed to fetch workflow data:', error)
        this.workflowData = null
      }
    },

    async fetchRunDetails(runId: string) {
      const projectsStore = useProjectsStore()
      if (!projectsStore.projectPath) return

      try {
        const response = await $fetch<RunDetails>(`/api/runs/${runId}`, {
          query: { project: projectsStore.projectPath },
        })
        this.currentRunDetails = response
      } catch (error) {
        console.error('Failed to fetch run details:', error)
        this.currentRunDetails = null
      }
    },

    clearCurrentRun() {
      this.currentRunId = null
      this.currentRunDetails = null
      this.workflowData = null
    },

    // WebSocket update handlers
    handleRunCreated(run: RunEntry) {
      this.runs.unshift(run)
    },

    handleRunUpdated(run: RunEntry) {
      const index = this.runs.findIndex(r => r.run_id === run.run_id)
      if (index !== -1) {
        this.runs[index] = run
      }
      // Update current run details if this is the selected run
      if (this.currentRunId === run.run_id && this.currentRunDetails) {
        this.currentRunDetails.entry = run
      }
    },

    handleNodeStarted(runId: string, nodeId: string) {
      if (this.currentRunId !== runId || !this.currentRunDetails) return

      // Initialize trace if not exists
      if (!this.currentRunDetails.traces[nodeId]) {
        this.currentRunDetails.traces[nodeId] = {
          id: nodeId,
          start_time: new Date().toISOString(),
          end_time: null,
          input: {},
          output: null,
          model: null,
          tokens: null,
          skipped: false,
          error: null,
          error_type: null,
          cost_usd: null,
          num_turns: null,
        }
      } else {
        this.currentRunDetails.traces[nodeId].start_time = new Date().toISOString()
      }
    },

    handleNodeCompleted(runId: string, nodeId: string, trace: NodeTrace) {
      if (this.currentRunId !== runId || !this.currentRunDetails) return
      this.currentRunDetails.traces[nodeId] = trace
    },

    handleNodeFailed(runId: string, nodeId: string, error: string) {
      if (this.currentRunId !== runId || !this.currentRunDetails) return

      if (this.currentRunDetails.traces[nodeId]) {
        this.currentRunDetails.traces[nodeId].error = error
        this.currentRunDetails.traces[nodeId].end_time = new Date().toISOString()
      }
    },

    handleCheckpointUpdated(runId: string, checkpoint: RunCheckpoint) {
      if (this.currentRunId !== runId || !this.currentRunDetails) return
      this.currentRunDetails.checkpoint = checkpoint
    },
  },
})

// Import the projects store for use in actions
import { useProjectsStore } from './projects'
