import { existsSync, readFileSync } from 'fs'
import { join, dirname } from 'path'
import { parse as parseYaml } from 'yaml'

interface WorkflowNode {
  id: string
  type: string
  label: string
  // From trace
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

interface WorkflowEdge {
  id: string
  source: string
  target: string
  mapping?: Record<string, string>
}

interface TraceNode {
  id: string
  start_time: string
  end_time: string
  input: Record<string, unknown>
  output: Record<string, unknown>
  model: string | null
  tokens: Record<string, number>
  skipped: boolean
  error: string | null
  error_type: string | null
}

interface Trace {
  run_id: string
  start_time: string
  end_time: string | null
  error: string | null
  nodes: TraceNode[]
}

interface AgentDefinition {
  trident: string
  name: string
  description?: string
  nodes: Record<string, { type: string; schema?: unknown }>
  edges: Record<string, { from: string; to: string; mapping?: Record<string, string> }>
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

  const runPath = join(projectPath, '.trident', 'runs', runId)
  const tracePath = join(runPath, 'trace.json')
  const metadataPath = join(runPath, 'metadata.json')
  const agentPath = join(projectPath, 'agent.tml')

  // Read trace data
  let trace: Trace | null = null
  if (existsSync(tracePath)) {
    try {
      trace = JSON.parse(readFileSync(tracePath, 'utf-8'))
    } catch (error) {
      console.error('Failed to parse trace:', error)
    }
  }

  // Read agent definition
  let agentDef: AgentDefinition | null = null
  if (existsSync(agentPath)) {
    try {
      const content = readFileSync(agentPath, 'utf-8')
      agentDef = parseYaml(content)
    } catch (error) {
      console.error('Failed to parse agent.tml:', error)
    }
  }

  // Build nodes from trace or agent definition
  const traceNodeMap = new Map<string, TraceNode>()
  if (trace?.nodes) {
    for (const node of trace.nodes) {
      traceNodeMap.set(node.id, node)
    }
  }

  // Get all node IDs from all sources (definition, trace, and edge references)
  const nodeIds = new Set<string>()
  if (agentDef?.nodes) {
    Object.keys(agentDef.nodes).forEach((id) => nodeIds.add(id))
  }
  if (trace?.nodes) {
    trace.nodes.forEach((n) => nodeIds.add(n.id))
  }
  // Also add any nodes referenced in edges but not in the nodes list
  if (agentDef?.edges) {
    for (const edge of Object.values(agentDef.edges)) {
      nodeIds.add(edge.from)
      nodeIds.add(edge.to)
    }
  }

  // Build workflow nodes
  const nodes: WorkflowNode[] = []
  for (const id of nodeIds) {
    const traceNode = traceNodeMap.get(id)
    const defNode = agentDef?.nodes?.[id]

    let status: WorkflowNode['status'] = 'pending'
    if (traceNode) {
      if (traceNode.error) {
        status = 'failed'
      } else if (traceNode.skipped) {
        status = 'skipped'
      } else if (traceNode.end_time) {
        status = 'completed'
      } else if (traceNode.start_time) {
        status = 'running'
      }
    }

    const startTime = traceNode?.start_time || null
    const endTime = traceNode?.end_time || null
    let duration: number | null = null
    if (startTime && endTime) {
      duration = new Date(endTime).getTime() - new Date(startTime).getTime()
    }

    nodes.push({
      id,
      type: defNode?.type || 'step',
      label: id,
      status,
      startTime,
      endTime,
      duration,
      input: traceNode?.input || null,
      output: traceNode?.output || null,
      error: traceNode?.error || null,
      model: traceNode?.model || null,
      tokens: traceNode?.tokens || {},
    })
  }

  // Build edges from agent definition
  const edges: WorkflowEdge[] = []
  if (agentDef?.edges) {
    for (const [edgeId, edge] of Object.entries(agentDef.edges)) {
      edges.push({
        id: edgeId,
        source: edge.from,
        target: edge.to,
        mapping: edge.mapping,
      })
    }
  } else {
    // Infer edges from trace order if no definition
    const nodeList = Array.from(nodeIds)
    for (let i = 0; i < nodeList.length - 1; i++) {
      edges.push({
        id: `e${i}`,
        source: nodeList[i],
        target: nodeList[i + 1],
      })
    }
  }

  return {
    runId,
    nodes,
    edges,
    startTime: trace?.start_time || null,
    endTime: trace?.end_time || null,
    error: trace?.error || null,
  }
})
