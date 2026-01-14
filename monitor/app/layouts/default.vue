<script setup lang="ts">
import { useUIStore } from '~/stores/ui'
import { useMediaQuery } from '@vueuse/core'

const ui = useUIStore()

// Responsive breakpoints
const isDesktop = useMediaQuery('(min-width: 1024px)')
const isTablet = useMediaQuery('(min-width: 768px)')

// Auto-close sidebar on mobile when navigating
const route = useRoute()
watch(() => route.fullPath, () => {
  if (!isDesktop.value && ui.sidebarOpen) {
    ui.sidebarOpen = false
  }
})

// Auto-close detail panel on mobile
watch(isDesktop, (desktop) => {
  if (!desktop) {
    ui.detailPanelOpen = false
  }
})

// Close mobile sidebar when clicking overlay
function closeMobileSidebar() {
  if (!isDesktop.value) {
    ui.sidebarOpen = false
  }
}
</script>

<template>
  <div class="flex h-screen flex-col overflow-hidden bg-background">
    <!-- Header -->
    <AppHeader />

    <!-- Main Content Area -->
    <div class="flex flex-1 overflow-hidden relative">
      <!-- Mobile Sidebar Overlay -->
      <Transition name="fade">
        <div
          v-if="ui.sidebarOpen && !isDesktop"
          class="absolute inset-0 z-20 bg-background/80 backdrop-blur-sm lg:hidden"
          @click="closeMobileSidebar"
        />
      </Transition>

      <!-- Left Sidebar -->
      <Transition name="slide-left">
        <aside
          v-if="ui.sidebarOpen"
          class="shrink-0 border-r bg-card overflow-y-auto z-30"
          :class="[
            isDesktop ? 'w-64 relative' : 'w-72 absolute inset-y-0 left-0 shadow-xl',
          ]"
        >
          <AppSidebar />
        </aside>
      </Transition>

      <!-- Center Content -->
      <main class="flex-1 overflow-hidden min-w-0">
        <slot />
      </main>

      <!-- Right Detail Panel -->
      <Transition name="slide-right">
        <aside
          v-if="ui.detailPanelOpen && isTablet"
          class="shrink-0 border-l bg-card overflow-y-auto"
          :class="[
            isDesktop ? 'w-[350px]' : 'w-[300px]',
          ]"
        >
          <DetailPanel />
        </aside>
      </Transition>
    </div>

    <!-- Mobile Detail Panel (Bottom Sheet) -->
    <Transition name="slide-up">
      <div
        v-if="ui.detailPanelOpen && ui.selectedNodeId && !isTablet"
        class="fixed inset-x-0 bottom-0 z-40 max-h-[60vh] border-t bg-card shadow-xl overflow-y-auto rounded-t-xl"
      >
        <DetailPanel />
      </div>
    </Transition>

    <!-- Toast Container -->
    <ToastContainer />

    <!-- Connection Status Banner -->
    <ConnectionBanner />
  </div>
</template>

<style scoped>
/* Fade transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Slide left transition (sidebar) */
.slide-left-enter-active,
.slide-left-leave-active {
  transition: transform 0.2s ease;
}
.slide-left-enter-from,
.slide-left-leave-to {
  transform: translateX(-100%);
}

/* Slide right transition (detail panel) */
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.2s ease;
}
.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
}

/* Slide up transition (mobile bottom sheet) */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.3s ease;
}
.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
}
</style>
