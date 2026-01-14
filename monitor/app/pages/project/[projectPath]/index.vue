<script setup lang="ts">
import { useProjectsStore } from '~/stores/projects'
import { useRunsStore } from '~/stores/runs'
import { useUIStore } from '~/stores/ui'

const projects = useProjectsStore()
const runs = useRunsStore()
const ui = useUIStore()
const { decodePath, navigateToRun } = useProjectPath()

const route = useRoute()

// Decode project path from URL and load project
const projectPath = computed(() => {
  const encoded = route.params.projectPath as string
  if (!encoded) return null
  try {
    return decodePath(encoded)
  } catch {
    return null
  }
})

// Load project on mount or when path changes
watch(projectPath, async (path) => {
  if (path && path !== projects.projectPath) {
    try {
      await projects.setProject(path)
      if (projects.projectPath) {
        await runs.fetchRuns(projects.projectPath)
        // Auto-select latest run if available
        if (runs.sortedRuns.length > 0) {
          const latestRun = runs.sortedRuns[0]
          navigateToRun(path, latestRun.run_id)
        }
      }
    } catch (error) {
      ui.showError('Failed to load project')
      navigateTo('/')
    }
  }
}, { immediate: true })
</script>

<template>
  <div class="flex h-full items-center justify-center">
    <!-- Loading state -->
    <div v-if="projects.isLoading" class="text-center">
      <div class="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full mx-auto" />
      <p class="mt-4 text-sm text-muted-foreground">Loading project...</p>
    </div>

    <!-- Project loaded but no runs -->
    <div v-else-if="!runs.hasRuns" class="text-center">
      <Card class="max-w-md p-6">
        <CardHeader>
          <CardTitle class="text-xl">{{ projects.projectName }}</CardTitle>
          <CardDescription>
            No workflow runs found for this project
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p class="text-sm text-muted-foreground">
            Run your workflow to see execution history:
          </p>
          <pre class="mt-2 rounded bg-muted p-2 text-xs overflow-x-auto">cd {{ projectPath }}
python -m trident project run</pre>
        </CardContent>
      </Card>
    </div>

    <!-- Has runs - show selection prompt -->
    <div v-else class="text-center">
      <Card class="max-w-md p-6">
        <CardHeader>
          <CardTitle class="text-xl">{{ projects.projectName }}</CardTitle>
          <CardDescription>
            Select a run from the sidebar to view details
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p class="text-sm text-muted-foreground">
            {{ runs.runs.length }} run{{ runs.runs.length === 1 ? '' : 's' }} available
          </p>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
