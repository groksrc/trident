import { existsSync, readFileSync, writeFileSync, rmSync } from 'fs'
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
  const runId = getRouterParam(event, 'runId')
  const query = getQuery(event)
  const projectPath = query.project as string

  if (!projectPath) {
    throw createError({
      statusCode: 400,
      message: 'Project path is required',
    })
  }

  if (!runId) {
    throw createError({
      statusCode: 400,
      message: 'Run ID is required',
    })
  }

  const manifestPath = join(projectPath, '.trident', 'runs', 'manifest.json')
  const runDir = join(projectPath, '.trident', 'runs', runId)

  // Remove from manifest
  if (existsSync(manifestPath)) {
    try {
      const content = readFileSync(manifestPath, 'utf-8')
      const manifest: RunManifest = JSON.parse(content)

      const originalLength = manifest.runs.length
      manifest.runs = manifest.runs.filter(r => r.run_id !== runId)

      if (manifest.runs.length === originalLength) {
        throw createError({
          statusCode: 404,
          message: 'Run not found in manifest',
        })
      }

      writeFileSync(manifestPath, JSON.stringify(manifest, null, 2))
    } catch (error: any) {
      if (error.statusCode === 404) throw error
      console.error('Failed to update manifest:', error)
      throw createError({
        statusCode: 500,
        message: 'Failed to update manifest',
      })
    }
  }

  // Delete run directory
  if (existsSync(runDir)) {
    try {
      rmSync(runDir, { recursive: true, force: true })
    } catch (error) {
      console.error('Failed to delete run directory:', error)
      // Don't fail if directory deletion fails - manifest was already updated
    }
  }

  return { success: true, runId }
})
