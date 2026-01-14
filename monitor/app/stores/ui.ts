import { defineStore } from 'pinia'

export interface Toast {
  id: string
  message: string
  type: 'info' | 'success' | 'warning' | 'error'
  duration?: number
}

interface UIState {
  sidebarOpen: boolean
  detailPanelOpen: boolean
  selectedNodeId: string | null
  toasts: Toast[]
  isConnected: boolean
  isReconnecting: boolean
}

export const useUIStore = defineStore('ui', {
  state: (): UIState => ({
    sidebarOpen: true,
    detailPanelOpen: true,
    selectedNodeId: null,
    toasts: [],
    isConnected: false,
    isReconnecting: false,
  }),

  actions: {
    toggleSidebar() {
      this.sidebarOpen = !this.sidebarOpen
    },

    toggleDetailPanel() {
      this.detailPanelOpen = !this.detailPanelOpen
    },

    selectNode(nodeId: string | null) {
      this.selectedNodeId = nodeId
      if (nodeId && !this.detailPanelOpen) {
        this.detailPanelOpen = true
      }
    },

    addToast(toast: Omit<Toast, 'id'>) {
      const id = crypto.randomUUID()
      const newToast: Toast = { ...toast, id }
      this.toasts.push(newToast)

      // Auto-remove after duration (default 5s)
      const duration = toast.duration ?? 5000
      setTimeout(() => {
        this.removeToast(id)
      }, duration)
    },

    removeToast(id: string) {
      this.toasts = this.toasts.filter(t => t.id !== id)
    },

    setConnectionStatus(connected: boolean) {
      this.isConnected = connected
      if (connected) {
        this.isReconnecting = false
      }
    },

    setReconnecting(reconnecting: boolean) {
      this.isReconnecting = reconnecting
    },

    // Convenience methods for toasts
    showError(message: string) {
      this.addToast({ message, type: 'error' })
    },

    showSuccess(message: string) {
      this.addToast({ message, type: 'success' })
    },

    showInfo(message: string) {
      this.addToast({ message, type: 'info' })
    },

    showWarning(message: string) {
      this.addToast({ message, type: 'warning' })
    },
  },
})
