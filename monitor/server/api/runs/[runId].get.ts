import { existsSync, readFileSync } from 'fs'
import { join } from 'path'

interface RunEntry {
  run_id: string
  project_name: string
  entrypoint: string | null
  status: 'running' | 'completed' | 'failed' | 'interrupted'
  started_at: string
  ended_at: string | null
  success: boolean | null
  error_summary: string | null
}

interface NodeTrace {
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

interface RunCheckpoint {
  run_id: string
  status: string
  completed_nodes: Record<string, { output: Record<string, unknown> }>
  pending_nodes: string[]
  total_cost_usd: number
}

interface TraceFile {
  run_id: string
  project_name: string
  started_at: string
  ended_at?: string
  nodes: Record<string, NodeTrace>
}

export default defineEventHandler(async (event) => {
  const runId = getRouterParam(event, 'runId')
  const query = getQuery(event)
  const projectPath = query.project as string

  if (!projectPath) {
    throw createError({
      statusCode: 400,
      message: 'Project path is required',
    })
  }

  if (!runId) {
    throw createError({
      statusCode: 400,
      message: 'Run ID is required',
    })
  }

  const runDir = join(projectPath, '.trident', 'runs', runId)

  if (!existsSync(runDir)) {
    throw createError({
      statusCode: 404,
      message: 'Run not found',
    })
  }

  // Read manifest to get entry
  const manifestPath = join(projectPath, '.trident', 'runs', 'manifest.json')
  let entry: RunEntry | null = null

  if (existsSync(manifestPath)) {
    try {
      const manifestContent = readFileSync(manifestPath, 'utf-8')
      const manifest = JSON.parse(manifestContent)
      entry = manifest.runs.find((r: RunEntry) => r.run_id === runId) || null
    } catch {
      // Continue without entry
    }
  }

  // Read checkpoint
  let checkpoint: RunCheckpoint | null = null
  const checkpointPath = join(runDir, 'checkpoint.json')

  if (existsSync(checkpointPath)) {
    try {
      const checkpointContent = readFileSync(checkpointPath, 'utf-8')
      checkpoint = JSON.parse(checkpointContent)
    } catch {
      // Continue without checkpoint
    }
  }

  // Read trace
  let traces: Record<string, NodeTrace> = {}
  const tracePath = join(runDir, 'trace.json')

  if (existsSync(tracePath)) {
    try {
      const traceContent = readFileSync(tracePath, 'utf-8')
      const traceFile: TraceFile = JSON.parse(traceContent)
      traces = traceFile.nodes || {}
    } catch {
      // Continue without traces
    }
  }

  // Construct a default entry if not found
  if (!entry) {
    entry = {
      run_id: runId,
      project_name: 'Unknown',
      entrypoint: null,
      status: checkpoint?.status as RunEntry['status'] || 'running',
      started_at: new Date().toISOString(),
      ended_at: null,
      success: null,
      error_summary: null,
    }
  }

  return {
    entry,
    checkpoint,
    traces,
  }
})
