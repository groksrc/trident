import { existsSync, readFileSync, readdirSync } from 'fs'
import { join } from 'path'

interface PromptData {
  nodeId: string
  name?: string
  description?: string
  promptTemplate: string
  frontmatter: Record<string, unknown>
  filePath: string
}

export default defineEventHandler(async (event): Promise<PromptData> => {
  const nodeId = getRouterParam(event, 'nodeId')
  const query = getQuery(event)
  const projectPath = query.project as string

  if (!projectPath) {
    throw createError({
      statusCode: 400,
      message: 'Project path is required',
    })
  }

  if (!nodeId) {
    throw createError({
      statusCode: 400,
      message: 'Node ID is required',
    })
  }

  const promptsDir = join(projectPath, 'prompts')

  if (!existsSync(promptsDir)) {
    throw createError({
      statusCode: 404,
      message: 'No prompts directory found',
    })
  }

  // Look for a prompt file matching the node ID
  const promptFiles = readdirSync(promptsDir).filter(f => f.endsWith('.prompt'))
  const promptFile = promptFiles.find(f => f.replace('.prompt', '') === nodeId)

  if (!promptFile) {
    throw createError({
      statusCode: 404,
      message: `No prompt found for node: ${nodeId}`,
    })
  }

  const promptPath = join(promptsDir, promptFile)
  const content = readFileSync(promptPath, 'utf-8')

  // Parse frontmatter and body
  const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/)

  if (!frontmatterMatch) {
    // No frontmatter, just return the content as template
    return {
      nodeId,
      promptTemplate: content.trim(),
      frontmatter: {},
      filePath: promptPath,
    }
  }

  const [, frontmatterYaml, promptTemplate] = frontmatterMatch

  // Parse YAML frontmatter (simple parsing)
  const frontmatter: Record<string, unknown> = {}
  const lines = frontmatterYaml.split('\n')
  let currentKey = ''
  let currentIndent = 0

  for (const line of lines) {
    const keyMatch = line.match(/^(\w+):\s*(.*)$/)
    if (keyMatch) {
      currentKey = keyMatch[1]
      const value = keyMatch[2].trim()
      if (value) {
        frontmatter[currentKey] = value
      } else {
        frontmatter[currentKey] = {}
      }
      currentIndent = 0
    }
  }

  return {
    nodeId,
    name: frontmatter.name as string | undefined,
    description: frontmatter.description as string | undefined,
    promptTemplate: promptTemplate.trim(),
    frontmatter,
    filePath: promptPath,
  }
})
