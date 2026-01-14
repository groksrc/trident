import { useUIStore } from '~/stores/ui'
import { useRunsStore } from '~/stores/runs'
import { useProjectsStore } from '~/stores/projects'

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let pingInterval: ReturnType<typeof setInterval> | null = null

export function useWebSocketConnection() {
  const ui = useUIStore()
  const runs = useRunsStore()
  const projects = useProjectsStore()

  function connect() {
    if (ws?.readyState === WebSocket.OPEN) return

    // Determine WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`

    try {
      ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        console.log('WebSocket connected')
        ui.setConnectionStatus(true)

        // Subscribe to current project if one is selected
        if (projects.projectPath) {
          subscribeToProject(projects.projectPath, runs.currentRunId)
        }

        // Start ping interval
        if (pingInterval) clearInterval(pingInterval)
        pingInterval = setInterval(() => {
          if (ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }))
          }
        }, 30000)
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          handleMessage(data)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }

      ws.onclose = () => {
        console.log('WebSocket disconnected')
        ui.setConnectionStatus(false)
        scheduleReconnect()
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        ui.setConnectionStatus(false)
      }
    } catch (error) {
      console.error('Failed to create WebSocket:', error)
      scheduleReconnect()
    }
  }

  function disconnect() {
    if (pingInterval) {
      clearInterval(pingInterval)
      pingInterval = null
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.close()
      ws = null
    }
    ui.setConnectionStatus(false)
  }

  function scheduleReconnect() {
    if (reconnectTimer) return

    ui.setReconnecting(true)
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, 3000)
  }

  function subscribeToProject(projectPath: string, runId: string | null = null) {
    if (ws?.readyState !== WebSocket.OPEN) return

    ws.send(JSON.stringify({
      type: 'subscribe_project',
      projectPath,
      runId,
    }))
  }

  function subscribeToRun(runId: string) {
    if (ws?.readyState !== WebSocket.OPEN) return

    ws.send(JSON.stringify({
      type: 'subscribe_run',
      runId,
    }))
  }

  function handleMessage(data: any) {
    switch (data.type) {
      case 'connected':
        console.log('WebSocket client ID:', data.clientId)
        break

      case 'subscribed':
        console.log('Subscribed to project:', data.projectPath)
        break

      case 'subscribed_run':
        console.log('Subscribed to run:', data.runId)
        break

      case 'manifest_updated':
        // Update runs list
        if (data.runs) {
          runs.$patch({ runs: data.runs })
        }
        break

      case 'trace_updated':
        // Update workflow data if this is the current run
        if (data.runId === runs.currentRunId && data.trace) {
          // Refresh workflow data
          runs.fetchWorkflowData(data.runId)
        }
        break

      case 'checkpoint_updated':
        if (data.runId === runs.currentRunId && data.checkpoint) {
          runs.handleCheckpointUpdated(data.runId, data.checkpoint)
        }
        break

      case 'pong':
        // Connection is alive
        break

      default:
        console.log('Unknown WebSocket message:', data.type)
    }
  }

  return {
    connect,
    disconnect,
    subscribeToProject,
    subscribeToRun,
  }
}
