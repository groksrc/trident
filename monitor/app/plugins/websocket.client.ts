export default defineNuxtPlugin(() => {
  const { connect, disconnect, subscribeToProject } = useWebSocketConnection()

  // Connect on app mount
  onNuxtReady(() => {
    connect()
  })

  // Disconnect on page unload
  if (import.meta.client) {
    window.addEventListener('beforeunload', () => {
      disconnect()
    })
  }
})
