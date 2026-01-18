<script setup lang="ts">
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import type { Node, Edge, NodeMouseEvent } from '@vue-flow/core'
import WorkflowNode from './WorkflowNode.vue'

interface WorkflowNodeData {
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

interface WorkflowEdgeData {
  id: string
  source: string
  target: string
  mapping?: Record<string, string>
}

interface Props {
  nodes: WorkflowNodeData[]
  edges: WorkflowEdgeData[]
  selectedNodeId?: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'node-click': [node: WorkflowNodeData]
}>()

const { fitView } = useVueFlow()

// Convert workflow nodes to Vue Flow format with auto-layout
const flowNodes = computed<Node[]>(() => {
  const nodeMap = new Map<string, WorkflowNodeData>()
  props.nodes.forEach((n) => nodeMap.set(n.id, n))

  // Build adjacency for layout
  const incoming = new Map<string, string[]>()
  const outgoing = new Map<string, string[]>()
  props.nodes.forEach((n) => {
    incoming.set(n.id, [])
    outgoing.set(n.id, [])
  })
  props.edges.forEach((e) => {
    incoming.get(e.target)?.push(e.source)
    outgoing.get(e.source)?.push(e.target)
  })

  // Find root nodes (no incoming edges)
  const roots = props.nodes.filter((n) => incoming.get(n.id)?.length === 0)

  // Calculate levels using BFS
  const levels = new Map<string, number>()
  const queue = [...roots.map((r) => r.id)]
  roots.forEach((r) => levels.set(r.id, 0))

  while (queue.length > 0) {
    const nodeId = queue.shift()!
    const level = levels.get(nodeId) || 0
    const children = outgoing.get(nodeId) || []
    for (const child of children) {
      const existingLevel = levels.get(child)
      if (existingLevel === undefined || existingLevel < level + 1) {
        levels.set(child, level + 1)
      }
      if (!queue.includes(child)) {
        queue.push(child)
      }
    }
  }

  // Group nodes by level
  const levelGroups = new Map<number, string[]>()
  levels.forEach((level, nodeId) => {
    if (!levelGroups.has(level)) {
      levelGroups.set(level, [])
    }
    levelGroups.get(level)!.push(nodeId)
  })

  // Position nodes - top-to-bottom layout
  const nodeWidth = 200
  const nodeHeight = 100
  const horizontalSpacing = 100
  const verticalSpacing = 120

  const positions = new Map<string, { x: number; y: number }>()
  levelGroups.forEach((nodeIds, level) => {
    const totalWidth = nodeIds.length * nodeWidth + (nodeIds.length - 1) * horizontalSpacing
    const startX = -totalWidth / 2 + nodeWidth / 2
    nodeIds.forEach((nodeId, index) => {
      positions.set(nodeId, {
        x: startX + index * (nodeWidth + horizontalSpacing),
        y: level * (nodeHeight + verticalSpacing),
      })
    })
  })

  return props.nodes.map((node) => ({
    id: node.id,
    type: 'workflow',
    position: positions.get(node.id) || { x: 0, y: 0 },
    data: {
      label: node.label,
      type: node.type,
      status: node.status,
      duration: node.duration,
      model: node.model,
      tokens: node.tokens,
    },
    selected: node.id === props.selectedNodeId,
  }))
})

// Convert workflow edges to Vue Flow format
const flowEdges = computed<Edge[]>(() => {
  return props.edges.map((edge) => {
    // Find source node status for edge color
    const sourceNode = props.nodes.find((n) => n.id === edge.source)
    const isCompleted = sourceNode?.status === 'completed'
    const isFailed = sourceNode?.status === 'failed'

    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: 'smoothstep',
      animated: sourceNode?.status === 'running',
      style: {
        stroke: isFailed
          ? 'rgb(239 68 68)'
          : isCompleted
            ? 'rgb(34 197 94)'
            : 'rgb(156 163 175)',
        strokeWidth: 2,
      },
    }
  })
})

function handleNodeClick(event: NodeMouseEvent) {
  const nodeData = props.nodes.find((n) => n.id === event.node.id)
  if (nodeData) {
    emit('node-click', nodeData)
  }
}

// Fit view when nodes change
watch(
  () => props.nodes,
  () => {
    nextTick(() => {
      fitView({ padding: 0.2 })
    })
  },
  { immediate: true }
)
</script>

<template>
  <div class="h-full w-full">
    <VueFlow
      :nodes="flowNodes"
      :edges="flowEdges"
      :default-viewport="{ zoom: 1, x: 0, y: 0 }"
      :min-zoom="0.2"
      :max-zoom="2"
      fit-view-on-init
      @node-click="handleNodeClick"
    >
      <template #node-workflow="nodeProps">
        <WorkflowNode
          :data="nodeProps.data"
          :selected="nodeProps.selected"
        />
      </template>

      <Background pattern-color="hsl(var(--muted))" :gap="20" />
      <Controls position="bottom-right" />
      <MiniMap
        position="bottom-left"
        :node-color="(node: Node) => {
          switch (node.data?.status) {
            case 'completed':
              return 'rgb(34 197 94)'
            case 'failed':
              return 'rgb(239 68 68)'
            case 'running':
              return 'rgb(59 130 246)'
            default:
              return 'rgb(156 163 175)'
          }
        }"
      />
    </VueFlow>
  </div>
</template>

<style>
@import '@vue-flow/core/dist/style.css';
@import '@vue-flow/core/dist/theme-default.css';
@import '@vue-flow/controls/dist/style.css';
@import '@vue-flow/minimap/dist/style.css';

.vue-flow__minimap {
  background-color: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 0.5rem;
}

.vue-flow__controls {
  background-color: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 0.5rem;
  box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1);
}

.vue-flow__controls-button {
  background-color: hsl(var(--card));
  border-color: hsl(var(--border));
  color: hsl(var(--foreground));
}

.vue-flow__controls-button:hover {
  background-color: hsl(var(--accent));
}
</style>
