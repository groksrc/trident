<script setup lang="ts">
import { FolderOpen, ChevronDown, Home, RefreshCw, Play } from 'lucide-vue-next'
import { useProjectsStore } from '~/stores/projects'
import { useRunsStore } from '~/stores/runs'
import { useUIStore } from '~/stores/ui'

const projects = useProjectsStore()
const runs = useRunsStore()
const ui = useUIStore()
const { navigateToProject, navigateToRun } = useProjectPath()
const route = useRoute()

const showProjectSelector = ref(false)
const showPathInput = ref(false)
const pathInput = ref('')
const isValidating = ref(false)
const showNewRunDialog = ref(false)

// Load recent projects on mount
onMounted(() => {
  projects.loadRecentProjects()
})

// Close dropdown when clicking outside
function handleClickOutside(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (!target.closest('.project-selector')) {
    showProjectSelector.value = false
    showPathInput.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})

async function handleSelectProject(path: string) {
  isValidating.value = true
  try {
    await projects.setProject(path)
    showProjectSelector.value = false
    showPathInput.value = false
    pathInput.value = ''
    // Navigate to project and fetch runs
    navigateToProject(path)
  } catch (error) {
    ui.showError('Failed to load project')
  } finally {
    isValidating.value = false
  }
}

async function handleSubmitPath() {
  if (!pathInput.value.trim()) return
  await handleSelectProject(pathInput.value.trim())
}

async function handleSelectRun(runId: string) {
  if (!projects.projectPath) return
  await runs.selectRun(runId)
  navigateToRun(projects.projectPath, runId)
}

async function refreshRuns() {
  if (!projects.projectPath) return
  await runs.fetchRuns(projects.projectPath)
}

function goHome() {
  projects.clearProject()
  runs.clearCurrentRun()
  navigateTo('/')
}
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- Project Selector -->
    <div class="border-b p-3 project-selector">
      <div class="relative">
        <Button
          variant="outline"
          class="w-full justify-between"
          @click.stop="showProjectSelector = !showProjectSelector"
        >
          <span class="flex items-center gap-2 truncate">
            <FolderOpen class="h-4 w-4 shrink-0" />
            <span class="truncate">{{ projects.projectName }}</span>
          </span>
          <ChevronDown
            class="h-4 w-4 shrink-0 transition-transform"
            :class="{ 'rotate-180': showProjectSelector }"
          />
        </Button>

        <!-- Dropdown -->
        <div
          v-if="showProjectSelector"
          class="absolute left-0 right-0 top-full z-10 mt-1 rounded-md border bg-popover shadow-md"
        >
          <!-- Path Input Mode -->
          <div v-if="showPathInput" class="p-2">
            <form @submit.prevent="handleSubmitPath">
              <input
                v-model="pathInput"
                type="text"
                placeholder="/path/to/project"
                class="w-full rounded border bg-background px-2 py-1.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                :disabled="isValidating"
                autofocus
              />
              <div class="mt-2 flex gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  class="flex-1"
                  @click="showPathInput = false"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  class="flex-1"
                  :disabled="!pathInput.trim() || isValidating"
                >
                  {{ isValidating ? '...' : 'Open' }}
                </Button>
              </div>
            </form>
          </div>

          <!-- Normal Mode -->
          <div v-else class="p-1">
            <!-- Go Home -->
            <button
              class="flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent"
              @click="goHome"
            >
              <Home class="h-4 w-4" />
              Home
            </button>

            <!-- Recent Projects -->
            <div v-if="projects.recentProjects.length > 0" class="border-t my-1 pt-1">
              <div class="px-2 py-1 text-xs font-medium text-muted-foreground">
                Recent
              </div>
              <button
                v-for="project in projects.recentProjects"
                :key="project.path"
                class="flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent"
                :class="{ 'bg-accent': project.path === projects.projectPath }"
                @click="handleSelectProject(project.path)"
              >
                <FolderOpen class="h-4 w-4 shrink-0 text-muted-foreground" />
                <span class="truncate">{{ project.name }}</span>
              </button>
            </div>

            <!-- Open Folder -->
            <div class="border-t mt-1 pt-1">
              <button
                class="flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent"
                @click="showPathInput = true"
              >
                <FolderOpen class="h-4 w-4" />
                Open Folder...
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- New Run Button -->
    <div v-if="projects.hasProject" class="border-b p-3">
      <Button
        class="w-full"
        @click="showNewRunDialog = true"
      >
        <Play class="mr-2 h-4 w-4" />
        New Run
      </Button>
    </div>

    <!-- Run List -->
    <div class="flex-1 overflow-y-auto">
      <div class="p-2">
        <div class="mb-2 flex items-center justify-between px-1">
          <span class="text-xs font-medium text-muted-foreground">
            Runs
          </span>
          <button
            v-if="projects.hasProject"
            class="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            title="Refresh runs"
            @click="refreshRuns"
          >
            <RefreshCw class="h-3 w-3" :class="{ 'animate-spin': runs.isLoading }" />
          </button>
        </div>

        <!-- Loading state -->
        <div v-if="runs.isLoading" class="px-2 py-4 text-center text-sm text-muted-foreground">
          <div class="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full mx-auto" />
          <p class="mt-2">Loading...</p>
        </div>

        <!-- Empty state -->
        <div v-else-if="!runs.hasRuns" class="px-2 py-4 text-center text-sm text-muted-foreground">
          <p>No runs found</p>
          <p v-if="!projects.hasProject" class="mt-1 text-xs">
            Select a project to view runs
          </p>
        </div>

        <!-- Run list -->
        <div v-else class="space-y-1">
          <RunListItem
            v-for="run in runs.sortedRuns"
            :key="run.run_id"
            :run="run"
            :selected="run.run_id === runs.currentRunId"
            @select="handleSelectRun(run.run_id)"
          />
        </div>
      </div>
    </div>

    <!-- New Run Dialog -->
    <NewRunDialog
      :open="showNewRunDialog"
      @close="showNewRunDialog = false"
    />
  </div>
</template>
