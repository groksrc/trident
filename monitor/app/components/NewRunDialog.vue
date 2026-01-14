<script setup lang="ts">
import { X, Play, Loader2 } from 'lucide-vue-next'
import { useProjectsStore } from '~/stores/projects'
import { useRunsStore } from '~/stores/runs'
import { useUIStore } from '~/stores/ui'

interface SchemaField {
  name: string
  type: string
  description?: string
  required?: boolean
  default?: unknown
}

interface WorkflowSchema {
  name: string
  description?: string
  entrypoints: string[]
  inputs: SchemaField[]
}

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
  runStarted: [runId: string]
}>()

const projects = useProjectsStore()
const runs = useRunsStore()
const ui = useUIStore()
const { navigateToRun } = useProjectPath()

const isLoading = ref(false)
const isSubmitting = ref(false)
const schema = ref<WorkflowSchema | null>(null)
const formData = ref<Record<string, unknown>>({})
const error = ref<string | null>(null)

// Fetch schema when dialog opens
watch(() => props.open, async (isOpen) => {
  if (isOpen && projects.projectPath) {
    await fetchSchema()
  } else {
    // Reset form when closed
    formData.value = {}
    error.value = null
  }
}, { immediate: true })

async function fetchSchema() {
  if (!projects.projectPath) return

  isLoading.value = true
  error.value = null

  try {
    const response = await $fetch<WorkflowSchema>('/api/workflow/schema', {
      query: { project: projects.projectPath },
    })
    schema.value = response

    // Initialize form with defaults
    formData.value = {}
    for (const field of response.inputs) {
      if (field.default !== undefined) {
        formData.value[field.name] = field.default
      } else if (field.type === 'boolean') {
        formData.value[field.name] = false
      } else if (field.type === 'number' || field.type === 'integer') {
        formData.value[field.name] = 0
      } else {
        formData.value[field.name] = ''
      }
    }
  } catch (err) {
    console.error('Failed to fetch schema:', err)
    error.value = 'Failed to load workflow schema'
  } finally {
    isLoading.value = false
  }
}

async function handleSubmit() {
  if (!projects.projectPath) return

  isSubmitting.value = true
  error.value = null

  try {
    // Clean up form data - remove empty strings for optional fields
    const inputs: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(formData.value)) {
      const field = schema.value?.inputs.find(f => f.name === key)
      if (value !== '' || field?.required) {
        // Convert types as needed
        if (field?.type === 'number' || field?.type === 'integer') {
          inputs[key] = Number(value)
        } else if (field?.type === 'boolean') {
          inputs[key] = Boolean(value)
        } else if (field?.type === 'array' || field?.type === 'object') {
          try {
            inputs[key] = typeof value === 'string' ? JSON.parse(value) : value
          } catch {
            inputs[key] = value
          }
        } else {
          inputs[key] = value
        }
      }
    }

    const response = await $fetch<{ runId: string; status: string; message?: string }>(
      '/api/runs/start',
      {
        method: 'POST',
        body: {
          projectPath: projects.projectPath,
          inputs,
        },
      }
    )

    if (response.status === 'started') {
      ui.showSuccess(`Run started: ${response.runId.slice(0, 8)}...`)
      emit('runStarted', response.runId)
      emit('close')

      // Refresh runs list and navigate
      await runs.fetchRuns(projects.projectPath)
      await runs.selectRun(response.runId)
      navigateToRun(projects.projectPath, response.runId)
    } else {
      error.value = response.message || 'Failed to start run'
    }
  } catch (err: any) {
    console.error('Failed to start run:', err)
    error.value = err.data?.message || err.message || 'Failed to start run'
  } finally {
    isSubmitting.value = false
  }
}

function getInputType(fieldType: string): string {
  switch (fieldType) {
    case 'number':
    case 'integer':
      return 'number'
    case 'boolean':
      return 'checkbox'
    default:
      return 'text'
  }
}

function shouldUseTextarea(field: SchemaField): boolean {
  return field.type === 'string' && (
    field.name.toLowerCase().includes('text') ||
    field.name.toLowerCase().includes('content') ||
    field.name.toLowerCase().includes('body') ||
    field.name.toLowerCase().includes('message') ||
    field.description?.toLowerCase().includes('multiline') ||
    false
  )
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="open"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
        @click.self="emit('close')"
      >
        <div class="w-full max-w-lg rounded-lg border bg-card shadow-xl">
          <!-- Header -->
          <div class="flex items-center justify-between border-b px-4 py-3">
            <h2 class="text-lg font-semibold">Start New Run</h2>
            <button
              class="rounded p-1 hover:bg-accent"
              @click="emit('close')"
            >
              <X class="h-5 w-5" />
            </button>
          </div>

          <!-- Content -->
          <div class="max-h-[60vh] overflow-y-auto p-4">
            <!-- Loading -->
            <div v-if="isLoading" class="flex items-center justify-center py-8">
              <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
              <span class="ml-2 text-muted-foreground">Loading schema...</span>
            </div>

            <!-- Error -->
            <div v-else-if="error && !schema" class="rounded-lg bg-red-50 p-4 text-red-700">
              {{ error }}
            </div>

            <!-- Form -->
            <form v-else-if="schema" @submit.prevent="handleSubmit">
              <!-- Workflow info -->
              <div class="mb-4">
                <h3 class="font-medium">{{ schema.name }}</h3>
                <p v-if="schema.description" class="text-sm text-muted-foreground">
                  {{ schema.description }}
                </p>
              </div>

              <!-- No inputs message -->
              <div v-if="schema.inputs.length === 0" class="rounded-lg bg-muted p-4 text-sm">
                This workflow has no input parameters. Click "Start Run" to execute.
              </div>

              <!-- Input fields -->
              <div v-else class="space-y-4">
                <div v-for="field in schema.inputs" :key="field.name">
                  <label class="block">
                    <span class="text-sm font-medium">
                      {{ field.name }}
                      <span v-if="field.required" class="text-red-500">*</span>
                    </span>
                    <span v-if="field.description" class="block text-xs text-muted-foreground mb-1">
                      {{ field.description }}
                    </span>

                    <!-- Checkbox for boolean -->
                    <div v-if="field.type === 'boolean'" class="flex items-center gap-2 mt-1">
                      <input
                        v-model="formData[field.name]"
                        type="checkbox"
                        class="rounded border-input"
                      />
                      <span class="text-sm">{{ formData[field.name] ? 'Yes' : 'No' }}</span>
                    </div>

                    <!-- Textarea for long text -->
                    <textarea
                      v-else-if="shouldUseTextarea(field)"
                      v-model="formData[field.name]"
                      rows="3"
                      class="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                      :placeholder="field.description || `Enter ${field.name}`"
                      :required="field.required"
                    />

                    <!-- Regular input -->
                    <input
                      v-else
                      v-model="formData[field.name]"
                      :type="getInputType(field.type)"
                      class="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                      :placeholder="field.description || `Enter ${field.name}`"
                      :required="field.required"
                    />
                  </label>
                </div>
              </div>

              <!-- Submit error -->
              <div v-if="error" class="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
                {{ error }}
              </div>
            </form>
          </div>

          <!-- Footer -->
          <div class="flex items-center justify-end gap-2 border-t px-4 py-3">
            <Button variant="ghost" @click="emit('close')">
              Cancel
            </Button>
            <Button
              :disabled="isLoading || isSubmitting"
              @click="handleSubmit"
            >
              <Loader2 v-if="isSubmitting" class="mr-2 h-4 w-4 animate-spin" />
              <Play v-else class="mr-2 h-4 w-4" />
              {{ isSubmitting ? 'Starting...' : 'Start Run' }}
            </Button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
