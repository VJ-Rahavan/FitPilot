import type { UINode } from '../types/ui'

export interface ToolResult {
  id?: string
  name: string
  text: string
  components: UINode[]
  display: 'fragment' | 'full'
  is_error: boolean
}

export type ChatEvent =
  | { event: 'text'; data: { delta: string } }
  | { event: 'tool_start'; data: { id: string; name: string; args: Record<string, unknown> } }
  | { event: 'tool_result'; data: ToolResult }
  | { event: 'done'; data: { conversation_id: string; text: string } }
  | { event: 'error'; data: { message: string } }

/** POST /api/chat and call `onEvent` for each Server-Sent Event as it arrives. */
export async function streamChat(
  message: string,
  conversationId: string | null,
  onEvent: (e: ChatEvent) => void,
): Promise<void> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  })
  if (!response.ok || !response.body) {
    onEvent({ event: 'error', data: { message: `The assistant is unavailable (${response.status}).` } })
    return
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let end: number
    while ((end = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)
      let event = ''
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7)
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (event && data) onEvent({ event, data: JSON.parse(data) } as ChatEvent)
    }
  }
}

/** A button in a tool result: run the tool directly, no LLM round trip. */
export async function runAction(tool: string, args: Record<string, unknown>): Promise<ToolResult> {
  const response = await fetch('/api/action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool, args }),
  })
  if (!response.ok) throw new Error(`Action failed (${response.status})`)
  return (await response.json()) as ToolResult
}
