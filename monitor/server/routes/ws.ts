import { watch } from 'fs'
import { join } from 'path'
import { existsSync, readFileSync } from 'fs'

// Track active WebSocket connections
const clients = new Map<string, {
  peer: any
  projectPath: string
  runId: string | null
}>()

// Track file watchers
const watchers = new Map<string, ReturnType<typeof watch>>()

function parseManifest(manifestPath: string) {
  try {
    if (!existsSync(manifestPath)) return null
    return JSON.parse(readFileSync(manifestPath, 'utf-8'))
  } catch {
    return null
  }
}

function parseTrace(tracePath: string) {
  try {
    if (!existsSync(tracePath)) return null
    return JSON.parse(readFileSync(tracePath, 'utf-8'))
  } catch {
    return null
  }
}

function broadcastToProject(projectPath: string, message: any) {
  for (const [clientId, client] of clients) {
    if (client.projectPath === projectPath) {
      try {
        client.peer.send(JSON.stringify(message))
      } catch (error) {
        console.error(`Failed to send to client ${clientId}:`, error)
      }
    }
  }
}

function watchProject(projectPath: string) {
  const runsDir = join(projectPath, '.trident', 'runs')
  const manifestPath = join(runsDir, 'manifest.json')

  // Already watching this project
  if (watchers.has(projectPath)) return

  // Don't watch if runs directory doesn't exist
  if (!existsSync(runsDir)) return

  // Watch manifest for new runs
  try {
    const watcher = watch(runsDir, { recursive: true }, (eventType, filename) => {
      if (!filename) return

      // Manifest changed - new run or run status updated
      if (filename === 'manifest.json' || filename.endsWith('manifest.json')) {
        const manifest = parseManifest(manifestPath)
        if (manifest?.runs) {
          broadcastToProject(projectPath, {
            type: 'manifest_updated',
            runs: manifest.runs,
          })
        }
      }

      // Trace file changed - node updates
      if (filename.includes('trace.json')) {
        const parts = filename.split('/')
        const runId = parts[0]
        const tracePath = join(runsDir, runId, 'trace.json')
        const trace = parseTrace(tracePath)
        if (trace) {
          broadcastToProject(projectPath, {
            type: 'trace_updated',
            runId,
            trace,
          })
        }
      }

      // Checkpoint changed
      if (filename.includes('checkpoint.json')) {
        const parts = filename.split('/')
        const runId = parts[0]
        const checkpointPath = join(runsDir, runId, 'checkpoint.json')
        try {
          if (existsSync(checkpointPath)) {
            const checkpoint = JSON.parse(readFileSync(checkpointPath, 'utf-8'))
            broadcastToProject(projectPath, {
              type: 'checkpoint_updated',
              runId,
              checkpoint,
            })
          }
        } catch {
          // Ignore parse errors
        }
      }
    })

    watchers.set(projectPath, watcher)
    console.log(`Started watching: ${runsDir}`)
  } catch (error) {
    console.error(`Failed to watch ${runsDir}:`, error)
  }
}

function stopWatchingProject(projectPath: string) {
  // Check if any clients are still watching this project
  let hasClients = false
  for (const client of clients.values()) {
    if (client.projectPath === projectPath) {
      hasClients = true
      break
    }
  }

  // If no clients, stop watching
  if (!hasClients) {
    const watcher = watchers.get(projectPath)
    if (watcher) {
      watcher.close()
      watchers.delete(projectPath)
      console.log(`Stopped watching: ${projectPath}`)
    }
  }
}

export default defineWebSocketHandler({
  open(peer) {
    const clientId = crypto.randomUUID()
    clients.set(clientId, {
      peer,
      projectPath: '',
      runId: null,
    })
    peer.send(JSON.stringify({ type: 'connected', clientId }))
    console.log(`WebSocket client connected: ${clientId}`)
  },

  message(peer, message) {
    try {
      const data = JSON.parse(message.text())
      const clientId = findClientId(peer)

      if (!clientId) {
        console.error('Unknown peer')
        return
      }

      const client = clients.get(clientId)
      if (!client) return

      switch (data.type) {
        case 'subscribe_project': {
          const oldPath = client.projectPath
          client.projectPath = data.projectPath
          client.runId = data.runId || null

          // Stop watching old project if needed
          if (oldPath && oldPath !== data.projectPath) {
            stopWatchingProject(oldPath)
          }

          // Start watching new project
          watchProject(data.projectPath)

          peer.send(JSON.stringify({
            type: 'subscribed',
            projectPath: data.projectPath,
          }))
          break
        }

        case 'subscribe_run': {
          client.runId = data.runId
          peer.send(JSON.stringify({
            type: 'subscribed_run',
            runId: data.runId,
          }))
          break
        }

        case 'ping':
          peer.send(JSON.stringify({ type: 'pong' }))
          break
      }
    } catch (error) {
      console.error('WebSocket message error:', error)
    }
  },

  close(peer) {
    const clientId = findClientId(peer)
    if (clientId) {
      const client = clients.get(clientId)
      if (client) {
        stopWatchingProject(client.projectPath)
      }
      clients.delete(clientId)
      console.log(`WebSocket client disconnected: ${clientId}`)
    }
  },

  error(peer, error) {
    console.error('WebSocket error:', error)
  },
})

function findClientId(peer: any): string | null {
  for (const [clientId, client] of clients) {
    if (client.peer === peer) {
      return clientId
    }
  }
  return null
}
