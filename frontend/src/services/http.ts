export const requestWithTimeout = async (
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  timeoutMs: number,
): Promise<Response> => {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    return await fetch(input, { ...init, signal: controller.signal })
  } finally {
    window.clearTimeout(timeout)
  }
}

export const asRecord = (
  value: unknown,
  error: string,
): Record<string, unknown> => {
  if (typeof value !== 'object' || value === null) throw new Error(error)
  return value as Record<string, unknown>
}
