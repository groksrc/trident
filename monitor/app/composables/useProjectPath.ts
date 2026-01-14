/**
 * Composable for encoding/decoding project paths for URL routing.
 * Uses base64url encoding to safely include file paths in URLs.
 */
export function useProjectPath() {
  /**
   * Encode a file path for use in URL
   */
  function encodePath(path: string): string {
    if (import.meta.client) {
      return btoa(path).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
    }
    return Buffer.from(path).toString('base64url')
  }

  /**
   * Decode a URL-safe path back to file path
   */
  function decodePath(encoded: string): string {
    // Add back padding if needed
    const padded = encoded + '==='.slice((encoded.length + 3) % 4)
    const base64 = padded.replace(/-/g, '+').replace(/_/g, '/')

    if (import.meta.client) {
      return atob(base64)
    }
    return Buffer.from(base64, 'base64').toString('utf-8')
  }

  /**
   * Navigate to a project
   */
  function navigateToProject(path: string) {
    const encoded = encodePath(path)
    return navigateTo(`/project/${encoded}`)
  }

  /**
   * Navigate to a specific run
   */
  function navigateToRun(projectPath: string, runId: string) {
    const encoded = encodePath(projectPath)
    return navigateTo(`/project/${encoded}/run/${runId}`)
  }

  /**
   * Get project path from route params
   */
  function getProjectPathFromRoute(): string | null {
    const route = useRoute()
    const encoded = route.params.projectPath as string
    if (!encoded) return null
    try {
      return decodePath(encoded)
    } catch {
      return null
    }
  }

  /**
   * Get run ID from route params
   */
  function getRunIdFromRoute(): string | null {
    const route = useRoute()
    return (route.params.runId as string) || null
  }

  return {
    encodePath,
    decodePath,
    navigateToProject,
    navigateToRun,
    getProjectPathFromRoute,
    getRunIdFromRoute,
  }
}
