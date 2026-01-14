import { spawn } from 'child_process'
import { join } from 'path'
import { existsSync } from 'fs'

interface StartRunRequest {
  projectPath: string
  inputs?: Record<string, unknown>
  entrypoint?: string
}

interface StartRunResponse {
  runId: string
  status: 'started' | 'error'
  message?: string
}

export default defineEventHandler(async (event): Promise<StartRunResponse> => {
  const body = await readBody<StartRunRequest>(event)

  if (!body.projectPath) {
    throw createError({
      statusCode: 400,
      message: 'Project path is required',
    })
  }

  // Verify project exists
  const agentPath = join(body.projectPath, 'agent.tml')
  if (!existsSync(agentPath)) {
    throw createError({
      statusCode: 400,
      message: 'Invalid project: agent.tml not found',
    })
  }

  // Generate run ID
  const runId = crypto.randomUUID()

  // Build command arguments
  const args = ['project', 'run', body.projectPath, '--run-id', runId]

  // Add inputs if provided
  if (body.inputs && Object.keys(body.inputs).length > 0) {
    args.push('--input', JSON.stringify(body.inputs))
  }

  // Add entrypoint if provided
  if (body.entrypoint) {
    args.push('--entrypoint', body.entrypoint)
  }

  // Add verbose flag for better logging
  args.push('--verbose')

  // Find the trident command - search up the tree for the runtime directory
  function findRuntimePath(startPath: string): string | null {
    let currentPath = startPath
    for (let i = 0; i < 5; i++) { // Search up to 5 levels
      const runtimePath = join(currentPath, 'runtime')
      if (existsSync(join(runtimePath, 'pyproject.toml'))) {
        return runtimePath
      }
      const parentPath = join(currentPath, '..')
      if (parentPath === currentPath) break // Reached root
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
      // Use uv run with python -m trident from the runtime directory
      command = 'uv'
      commandArgs = ['run', '--directory', tridentPath, 'python', '-m', 'trident', ...args]
    } else {
      // Assume trident is installed globally or in PATH
      command = 'trident'
      commandArgs = args
    }

    console.log(`Starting run: ${command} ${commandArgs.join(' ')}`)

    const child = spawn(command, commandArgs, {
      cwd: body.projectPath,
      detached: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        // Ensure Python output is unbuffered for real-time updates
        PYTHONUNBUFFERED: '1',
      },
    })

    let started = false
    let errorOutput = ''

    child.stdout?.on('data', (data) => {
      const output = data.toString()
      console.log(`[trident:${runId.slice(0, 8)}] ${output}`)

      // Consider run started once we see any output
      if (!started) {
        started = true
        resolve({
          runId,
          status: 'started',
          message: 'Run started successfully',
        })
      }
    })

    child.stderr?.on('data', (data) => {
      const output = data.toString()
      console.error(`[trident:${runId.slice(0, 8)}:err] ${output}`)
      errorOutput += output
    })

    child.on('error', (error) => {
      console.error(`Failed to start trident: ${error.message}`)
      if (!started) {
        reject(createError({
          statusCode: 500,
          message: `Failed to start run: ${error.message}`,
        }))
      }
    })

    child.on('close', (code) => {
      console.log(`Run ${runId.slice(0, 8)} exited with code ${code}`)
      if (!started && code !== 0) {
        reject(createError({
          statusCode: 500,
          message: `Run failed to start: ${errorOutput || 'Unknown error'}`,
        }))
      }
    })

    // Unref so the parent process can exit independently
    child.unref()

    // Set a timeout to respond if process doesn't produce output quickly
    setTimeout(() => {
      if (!started) {
        started = true
        resolve({
          runId,
          status: 'started',
          message: 'Run started (waiting for output)',
        })
      }
    }, 2000)
  })
})
