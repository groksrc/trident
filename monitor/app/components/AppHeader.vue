<script setup lang="ts">
import { Menu, PanelRightClose, PanelRightOpen, X, Home } from 'lucide-vue-next'
import { useUIStore } from '~/stores/ui'
import { useProjectsStore } from '~/stores/projects'
import { useMediaQuery } from '@vueuse/core'

const ui = useUIStore()
const projects = useProjectsStore()
const isDesktop = useMediaQuery('(min-width: 1024px)')

function truncatePath(path: string, maxLength: number = 30): string {
  if (path.length <= maxLength) return path
  const parts = path.split('/')
  if (parts.length <= 2) return '...' + path.slice(-maxLength)
  return '.../' + parts.slice(-2).join('/')
}
</script>

<template>
  <header class="flex h-14 shrink-0 items-center border-b bg-card px-3 md:px-4 gap-2">
    <!-- Left: Menu toggle and logo -->
    <div class="flex items-center gap-2 md:gap-3">
      <Button
        variant="ghost"
        size="icon"
        @click="ui.toggleSidebar"
        aria-label="Toggle sidebar"
      >
        <X v-if="ui.sidebarOpen && !isDesktop" class="h-5 w-5" />
        <Menu v-else class="h-5 w-5" />
      </Button>

      <!-- Logo - hide text on mobile -->
      <NuxtLink to="/" class="flex items-center gap-2">
        <div class="flex items-center gap-2">
          <svg class="h-6 w-6 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
          <span class="hidden sm:inline text-lg font-semibold">Trident</span>
        </div>
      </NuxtLink>
    </div>

    <!-- Center: Current project info -->
    <div class="flex flex-1 items-center justify-center min-w-0">
      <div v-if="projects.currentProject" class="text-center truncate">
        <span class="text-sm font-medium">{{ projects.projectName }}</span>
        <span class="hidden md:inline text-xs text-muted-foreground ml-1" :title="projects.currentProject.path">
          ({{ truncatePath(projects.currentProject.path) }})
        </span>
      </div>
      <span v-else class="text-sm text-muted-foreground">
        <span class="hidden sm:inline">No project selected</span>
        <span class="sm:hidden">Select project</span>
      </span>
    </div>

    <!-- Right: Status and panel toggle -->
    <div class="flex items-center gap-1 md:gap-2">
      <!-- Connection status -->
      <div class="flex items-center gap-1.5 px-2 py-1 rounded text-xs">
        <span
          class="h-2 w-2 rounded-full"
          :class="ui.isConnected ? 'bg-green-500' : 'bg-gray-400'"
        />
        <span class="hidden md:inline text-muted-foreground">
          {{ ui.isConnected ? 'Connected' : 'Offline' }}
        </span>
      </div>

      <!-- Detail panel toggle -->
      <Button
        variant="ghost"
        size="icon"
        @click="ui.toggleDetailPanel"
        aria-label="Toggle detail panel"
        class="hidden md:flex"
      >
        <PanelRightClose v-if="ui.detailPanelOpen" class="h-5 w-5" />
        <PanelRightOpen v-else class="h-5 w-5" />
      </Button>
    </div>
  </header>
</template>
