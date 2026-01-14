<script setup lang="ts">
import { FolderOpen, Clock, ArrowRight } from 'lucide-vue-next'
import { useProjectsStore } from '~/stores/projects'
import { useUIStore } from '~/stores/ui'

const projects = useProjectsStore()
const ui = useUIStore()
const { navigateToProject } = useProjectPath()

const showProjectDialog = ref(false)
const projectPathInput = ref('')
const isValidating = ref(false)

// Load recent projects on mount
onMounted(() => {
  projects.loadRecentProjects()
})

async function handleSelectProject(path: string) {
  isValidating.value = true
  try {
    await projects.setProject(path)
    showProjectDialog.value = false
    projectPathInput.value = ''
    navigateToProject(path)
  } catch (error) {
    ui.showError(error instanceof Error ? error.message : 'Failed to load project')
  } finally {
    isValidating.value = false
  }
}

async function handleSubmitPath() {
  if (!projectPathInput.value.trim()) return
  await handleSelectProject(projectPathInput.value.trim())
}

function handleRecentProject(path: string) {
  handleSelectProject(path)
}
</script>

<template>
  <div class="flex h-full items-center justify-center p-8">
    <div class="w-full max-w-2xl">
      <!-- Welcome Card -->
      <Card class="p-6">
        <CardHeader class="text-center pb-2">
          <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
            <svg class="h-8 w-8 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <CardTitle class="text-2xl">Trident Monitor</CardTitle>
          <CardDescription class="text-base">
            Visualize and debug your Trident workflow executions
          </CardDescription>
        </CardHeader>

        <CardContent class="pt-6">
          <!-- Open Project Button -->
          <Button
            class="w-full h-12 text-base"
            @click="showProjectDialog = true"
          >
            <FolderOpen class="mr-2 h-5 w-5" />
            Open Project Folder
          </Button>

          <!-- Recent Projects -->
          <div v-if="projects.recentProjects.length > 0" class="mt-6">
            <h3 class="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
              <Clock class="h-4 w-4" />
              Recent Projects
            </h3>
            <div class="space-y-2">
              <button
                v-for="project in projects.recentProjects"
                :key="project.path"
                class="w-full flex items-center justify-between rounded-lg border p-3 text-left hover:bg-accent transition-colors group"
                @click="handleRecentProject(project.path)"
              >
                <div class="min-w-0 flex-1">
                  <p class="font-medium truncate">{{ project.name }}</p>
                  <p class="text-xs text-muted-foreground truncate">{{ project.path }}</p>
                </div>
                <ArrowRight class="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0 ml-2" />
              </button>
            </div>
          </div>

          <!-- Help text -->
          <div class="mt-6 text-center">
            <p class="text-xs text-muted-foreground">
              Select a folder containing an <code class="rounded bg-muted px-1 py-0.5">agent.tml</code> file
            </p>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- Project Path Dialog -->
    <Teleport to="body">
      <div
        v-if="showProjectDialog"
        class="fixed inset-0 z-50 flex items-center justify-center"
      >
        <!-- Backdrop -->
        <div
          class="absolute inset-0 bg-background/80 backdrop-blur-sm"
          @click="showProjectDialog = false"
        />

        <!-- Dialog -->
        <Card class="relative z-10 w-full max-w-md mx-4 p-6">
          <CardHeader class="pb-4">
            <CardTitle>Open Project</CardTitle>
            <CardDescription>
              Enter the path to your Trident project folder
            </CardDescription>
          </CardHeader>

          <CardContent>
            <form @submit.prevent="handleSubmitPath">
              <div class="space-y-4">
                <div>
                  <label for="projectPath" class="text-sm font-medium">
                    Project Path
                  </label>
                  <input
                    id="projectPath"
                    v-model="projectPathInput"
                    type="text"
                    placeholder="/path/to/your/project"
                    class="mt-1.5 w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                    :disabled="isValidating"
                  />
                  <p class="mt-1.5 text-xs text-muted-foreground">
                    Example: ~/code/trident/examples/structured-output
                  </p>
                </div>

                <div class="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    class="flex-1"
                    @click="showProjectDialog = false"
                    :disabled="isValidating"
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    class="flex-1"
                    :disabled="!projectPathInput.trim() || isValidating"
                  >
                    <span v-if="isValidating">Validating...</span>
                    <span v-else>Open</span>
                  </Button>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </Teleport>
  </div>
</template>
