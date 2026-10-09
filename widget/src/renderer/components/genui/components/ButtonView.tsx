import { cn } from '../../../lib/format'
import type { ButtonNode } from '../../../types/ui'
import { useUIAction } from '../useUIAction'

const VARIANTS = {
  primary: 'bg-brand text-brand-fg hover:bg-brand-dim',
  secondary: 'border border-border-strong bg-surface-2 text-fg hover:bg-surface-3',
  ghost: 'text-muted hover:bg-surface-2 hover:text-fg',
  danger: 'border border-bad/40 bg-bad/10 text-bad hover:bg-bad/20',
} as const

export function ButtonView({ node }: { node: ButtonNode }) {
  const { dispatch, disabled } = useUIAction()
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => dispatch({ action: node.action, payload: node.payload ?? {}, label: node.label })}
      className={cn(
        'inline-flex h-9 items-center justify-center self-start rounded-lg px-4 text-sm font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-50',
        VARIANTS[node.variant ?? 'primary'],
      )}
    >
      {node.label}
    </button>
  )
}
