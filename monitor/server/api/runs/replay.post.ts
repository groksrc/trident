import { spawn } from 'child_process'
import { join } from 'path'
import { existsSync } from 'fs'

interface ReplayRequest {
  projectPath: string
  runId: string
  startFrom: string
  modifiedInputs?: Record<string, unknown>
}

interface ReplayResponse {
  newRunId: string
  status: 'started' | 'error'
  message?: string
}

export default defineEventHandler(async (event): Promise<ReplayResponse> => {
  const body = await readBody<ReplayRequest>(event)

  if (!body.projectPath) {
    throw createError({
      statusCode: 400,
      message: 'Project path is required',
    })
  }

  if (!body.runId) {
    throw createError({
      statusCode: 400,
      message: 'Run ID is required for replay',
    })
  }

  if (!body.startFrom) {
    throw createError({
      statusCode: 400,
      message: 'Start from node is required',
    })
  }

  // Verify run exists
  const runDir = join(body.projectPath, '.trident', 'runs', body.runId)
  if (!existsSync(runDir)) {
    throw createError({
      statusCode: 404,
      message: `Run not found: ${body.runId}`,
    })
  }

  // Generate new run ID
  const newRunId = crypto.randomUUID()

  // Build command arguments for replay
  const args = [
    'project', 'run', body.projectPath,
    '--run-id', newRunId,
    '--resume', body.runId,
    '--start-from', body.startFrom,
    '--verbose',
  ]

  // Add modified inputs if provided
  if (body.modifiedInputs && Object.keys(body.modifiedInputs).length > 0) {
    args.push('--input', JSON.stringify(body.modifiedInputs))
  }

  // Find the trident command - search up the tree for the runtime directory
  function findRuntimePath(startPath: string): string | null {
    let currentPath = startPath
    for (let i = 0; i < 5; i++) {
      const runtimePath = join(currentPath, 'runtime')
      if (existsSync(join(runtimePath, 'pyproject.toml'))) {
        return runtimePath
      }
      const parentPath = join(currentPath, '..')
      if (parentPath === currentPath) break
      currentPath = parentPath
    }
    return null
  }

  const tridentPath = findRuntimePath(body.projectPath)
  const useUv = tridentPath !== null

  return new Promise((resolve, reject) => {
    let command: string
    let commandArgs: string[]

    if (useUv && tridentPath) {
      command = 'uv'
      commandArgs = ['run', '--directory', tridentPath, 'python', '-m', 'trident', ...args]
    } else {
      command = 'trident'
      commandArgs = args
    }

    console.log(`Starting replay: ${command} ${commandArgs.join(' ')}`)

    const child = spawn(command, commandArgs, {
      cwd: body.projectPath,
      detached: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
      },
    })

    let started = false
    let errorOutput = ''

    child.stdout?.on('data', (data) => {
      const output = data.toString()
      console.log(`[replay:${newRunId.slice(0, 8)}] ${output}`)

      if (!started) {
        started = true
        resolve({
          newRunId,
          status: 'started',
          message: `Replaying from node: ${body.startFrom}`,
        })
      }
    })

    child.stderr?.on('data', (data) => {
      const output = data.toString()
      console.error(`[replay:${newRunId.slice(0, 8)}:err] ${output}`)
      errorOutput += output
    })

    child.on('error', (error) => {
      console.error(`Failed to start replay: ${error.message}`)
      if (!started) {
        reject(createError({
          statusCode: 500,
          message: `Failed to start replay: ${error.message}`,
        }))
      }
    })

    child.on('close', (code) => {
      console.log(`Replay ${newRunId.slice(0, 8)} exited with code ${code}`)
      if (!started && code !== 0) {
        reject(createError({
          statusCode: 500,
          message: `Replay failed to start: ${errorOutput || 'Unknown error'}`,
        }))
      }
    })

    child.unref()

    // Timeout to respond if no output quickly
    setTimeout(() => {
      if (!started) {
        started = true
        resolve({
          newRunId,
          status: 'started',
          message: 'Replay started (waiting for output)',
        })
      }
    }, 2000)
  })
})
