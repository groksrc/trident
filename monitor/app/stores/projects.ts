import { defineStore } from 'pinia'

export interface TridentProject {
  path: string
  name: string
  lastOpened: string
}

interface ProjectsState {
  currentProject: TridentProject | null
  recentProjects: TridentProject[]
  isLoading: boolean
  error: string | null
}

export const useProjectsStore = defineStore('projects', {
  state: (): ProjectsState => ({
    currentProject: null,
    recentProjects: [],
    isLoading: false,
    error: null,
  }),

  getters: {
    hasProject: (state) => state.currentProject !== null,
    projectPath: (state) => state.currentProject?.path || null,
    projectName: (state) => state.currentProject?.name || 'No Project',
  },

  actions: {
    async setProject(path: string) {
      this.isLoading = true
      this.error = null

      try {
        // Validate the project path via API
        const response = await $fetch<{ valid: boolean; name: string }>('/api/projects/validate', {
          method: 'POST',
          body: { path },
        })

        if (!response.valid) {
          throw new Error('Invalid Trident project: agent.tml not found')
        }

        const project: TridentProject = {
          path,
          name: response.name,
          lastOpened: new Date().toISOString(),
        }

        this.currentProject = project
        this.addToRecent(project)
        this.saveRecentProjects()
      } catch (error) {
        this.error = error instanceof Error ? error.message : 'Failed to load project'
        throw error
      } finally {
        this.isLoading = false
      }
    },

    clearProject() {
      this.currentProject = null
    },

    addToRecent(project: TridentProject) {
      // Remove if already exists
      this.recentProjects = this.recentProjects.filter(p => p.path !== project.path)
      // Add to beginning
      this.recentProjects.unshift(project)
      // Keep only 5 most recent
      this.recentProjects = this.recentProjects.slice(0, 5)
    },

    loadRecentProjects() {
      if (import.meta.client) {
        const stored = localStorage.getItem('trident-recent-projects')
        if (stored) {
          try {
            this.recentProjects = JSON.parse(stored)
          } catch {
            this.recentProjects = []
          }
        }
      }
    },

    saveRecentProjects() {
      if (import.meta.client) {
        localStorage.setItem('trident-recent-projects', JSON.stringify(this.recentProjects))
      }
    },

    removeFromRecent(path: string) {
      this.recentProjects = this.recentProjects.filter(p => p.path !== path)
      this.saveRecentProjects()
    },
  },
})
