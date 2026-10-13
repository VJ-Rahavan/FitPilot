import { formatValue } from '../../../lib/format'
import type { ProgressNode } from '../../../types/ui'

export function ProgressView({ node }: { node: ProgressNode }) {
  const max = node.max && node.max > 0 ? node.max : 100
  const pct = Math.min(Math.max((node.value / max) * 100, 0), 100)
  return (
    <div className="rounded-2xl border border-border bg-surface p-4">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium">{node.label}</span>
        <span className="text-muted tabular-nums">
          {formatValue(node.value)} / {formatValue(max)}
          {node.unit ? ` ${node.unit}` : ''}
        </span>
      </div>
      <div
        className="mt-2.5 h-2 overflow-hidden rounded-full bg-surface-3"
        role="progressbar"
        aria-valuenow={node.value}
        aria-valuemax={max}
      >
        <div
          className="h-full rounded-full bg-brand transition-[width] duration-700"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-1.5 flex justify-between text-xs text-muted">
        <span>{node.caption}</span>
        <span className="tabular-nums">{Math.round(pct)}%</span>
      </div>
    </div>
  )
}
