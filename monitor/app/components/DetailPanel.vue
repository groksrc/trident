<script setup lang="ts">
import { X, Copy, Check } from 'lucide-vue-next'
import { useUIStore } from '~/stores/ui'
import { useRunsStore } from '~/stores/runs'

const ui = useUIStore()
const runs = useRunsStore()

const copied = ref(false)

// Get selected node from workflow data
const selectedNode = computed(() => {
  if (!ui.selectedNodeId || !runs.workflowData) return null
  return runs.workflowData.nodes.find(n => n.id === ui.selectedNodeId) || null
})

async function copyOutput() {
  if (!selectedNode.value?.output) return

  try {
    await navigator.clipboard.writeText(JSON.stringify(selectedNode.value.output, null, 2))
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    ui.showError('Failed to copy to clipboard')
  }
}

function closePanel() {
  ui.selectNode(null)
  ui.toggleDetailPanel()
}
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between border-b px-4 py-3">
      <h2 class="text-sm font-medium">Node Details</h2>
      <Button
        variant="ghost"
        size="icon"
        class="h-6 w-6"
        @click="closePanel"
      >
        <X class="h-4 w-4" />
      </Button>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto">
      <!-- No node selected -->
      <div v-if="!ui.selectedNodeId" class="py-8 text-center text-sm text-muted-foreground">
        <p>Select a node to view details</p>
        <p class="mt-1 text-xs">Click on any node in the workflow diagram</p>
      </div>

      <!-- Node details using NodeDetail component -->
      <NodeDetail v-else-if="selectedNode" :node="selectedNode" />

      <!-- Node not found -->
      <div v-else class="py-8 text-center text-sm text-muted-foreground">
        <p>Node: {{ ui.selectedNodeId }}</p>
        <p class="mt-1 text-xs">Loading...</p>
      </div>
    </div>
  </div>
</template>
