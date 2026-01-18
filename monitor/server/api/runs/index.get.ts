import { existsSync, readFileSync } from 'fs'
import { join } from 'path'

interface RunEntry {
  run_id: string
  project_name: string
  entrypoint: string | null
  status: 'running' | 'completed' | 'failed' | 'interrupted'
  started_at: string
  ended_at: string | null
  success: boolean | null
  error_summary: string | null
}

interface RunManifest {
  version: string
  runs: RunEntry[]
}

export default defineEventHandler(async (event) => {
  const query = getQuery(event)
  const projectPath = query.project as string

  if (!projectPath) {
    throw createError({
      statusCode: 400,
      message: 'Project path is required',
    })
  }

  const manifestPath = join(projectPath, '.trident', 'runs', 'manifest.json')

  if (!existsSync(manifestPath)) {
    return { runs: [] }
  }

  try {
    const content = readFileSync(manifestPath, 'utf-8')
    const manifest: RunManifest = JSON.parse(content)

    // Staleness threshold: runs "running" for more than 1 hour are likely stale
    const STALE_THRESHOLD_MS = 60 * 60 * 1000 // 1 hour
    const now = Date.now()

    // Deduplicate runs - keep the most recent entry for each run_id
    const seenIds = new Map<string, RunEntry>()
    for (const run of manifest.runs) {
      const existing = seenIds.get(run.run_id)
      if (!existing) {
        seenIds.set(run.run_id, run)
      } else {
        // Keep the entry with the later started_at, or the non-running one if times are equal
        const existingTime = new Date(existing.started_at).getTime()
        const currentTime = new Date(run.started_at).getTime()
        if (currentTime > existingTime || (existing.status === 'running' && run.status !== 'running')) {
          seenIds.set(run.run_id, run)
        }
      }
    }

    // Mark stale "running" runs as interrupted
    const runs = Array.from(seenIds.values())
      .map((run) => {
        if (run.status === 'running') {
          const startedAt = new Date(run.started_at).getTime()
          if (now - startedAt > STALE_THRESHOLD_MS) {
            return {
              ...run,
              status: 'interrupted' as const,
              error_summary: 'Run appears stale (no activity for 1+ hour)',
            }
          }
        }
        return run
      })
      .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime())
      .slice(0, 50)

    return { runs }
  } catch (error) {
    console.error('Failed to read manifest:', error)
    return { runs: [] }
  }
})
