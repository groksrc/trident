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

    // Return most recent 50 runs, sorted by started_at descending
    const runs = manifest.runs
      .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime())
      .slice(0, 50)

    return { runs }
  } catch (error) {
    console.error('Failed to read manifest:', error)
    return { runs: [] }
  }
})
