/** A button press in a tool result: call MCP tool `action` with `payload` as arguments. */
export interface UIEventInput {
  action: string
  payload: Record<string, unknown>
  label?: string
}
