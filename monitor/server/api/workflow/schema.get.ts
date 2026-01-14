import { existsSync, readFileSync } from 'fs'
import { join } from 'path'
import { parse as parseYaml } from 'yaml'

interface SchemaField {
  name: string
  type: string
  description?: string
  required?: boolean
  default?: unknown
}

interface WorkflowSchema {
  name: string
  description?: string
  entrypoints: string[]
  inputs: SchemaField[]
}

interface AgentDefinition {
  trident: string
  name: string
  description?: string
  entrypoints?: string[]
  nodes: Record<string, {
    type: string
    schema?: Record<string, {
      type: string
      description?: string
      required?: boolean
      default?: unknown
    }>
  }>
}

export default defineEventHandler(async (event): Promise<WorkflowSchema> => {
  const query = getQuery(event)
  const projectPath = query.project as string

  if (!projectPath) {
    throw createError({
      statusCode: 400,
      message: 'Project path is required',
    })
  }

  const agentPath = join(projectPath, 'agent.tml')

  if (!existsSync(agentPath)) {
    throw createError({
      statusCode: 404,
      message: 'agent.tml not found',
    })
  }

  try {
    const content = readFileSync(agentPath, 'utf-8')
    const agentDef: AgentDefinition = parseYaml(content)

    // Find input nodes and their schemas
    const inputs: SchemaField[] = []
    const entrypoints = agentDef.entrypoints || []

    // Look for input-type nodes
    for (const [nodeId, node] of Object.entries(agentDef.nodes || {})) {
      if (node.type === 'input' && node.schema) {
        // This is an input node with a schema
        for (const [fieldName, fieldDef] of Object.entries(node.schema)) {
          inputs.push({
            name: fieldName,
            type: fieldDef.type || 'string',
            description: fieldDef.description,
            required: fieldDef.required !== false, // default to required
            default: fieldDef.default,
          })
        }
        // Add to entrypoints if not already there
        if (!entrypoints.includes(nodeId)) {
          entrypoints.push(nodeId)
        }
      }
    }

    return {
      name: agentDef.name,
      description: agentDef.description,
      entrypoints,
      inputs,
    }
  } catch (error) {
    console.error('Failed to parse agent.tml:', error)
    throw createError({
      statusCode: 500,
      message: 'Failed to parse workflow schema',
    })
  }
})
