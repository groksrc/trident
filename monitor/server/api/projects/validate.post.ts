import { existsSync, readFileSync } from 'fs'
import { join, basename } from 'path'
import { parse } from 'yaml'

interface ValidateBody {
  path: string
}

export default defineEventHandler(async (event) => {
  const body = await readBody<ValidateBody>(event)

  if (!body.path) {
    throw createError({
      statusCode: 400,
      message: 'Path is required',
    })
  }

  const agentPath = join(body.path, 'agent.tml')

  // Check if agent.tml exists
  if (!existsSync(agentPath)) {
    return {
      valid: false,
      name: null,
      error: 'agent.tml not found',
    }
  }

  // Try to parse the agent.tml to extract the name
  try {
    const content = readFileSync(agentPath, 'utf-8')
    const parsed = parse(content)
    const name = parsed.name || basename(body.path)

    return {
      valid: true,
      name,
    }
  } catch (error) {
    return {
      valid: false,
      name: null,
      error: 'Failed to parse agent.tml',
    }
  }
})
