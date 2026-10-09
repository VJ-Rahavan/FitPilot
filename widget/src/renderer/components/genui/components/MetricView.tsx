import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import { cn, formatValue } from '../../../lib/format'
import type { MetricNode } from '../../../types/ui'
import { ICONS } from '../../../lib/icons'

export function MetricView({ node }: { node: MetricNode }) {
  const Icon = node.icon ? ICONS[node.icon] : null
  const change = node.change_pct
  const hasChange = typeof change === 'number' && Number.isFinite(change)
  const isGood = hasChange && (node.good_direction === 'down' ? change < 0 : change > 0)
  const Arrow = !hasChange || change === 0 ? Minus : change > 0 ? ArrowUpRight : ArrowDownRight

  return (
    <div className="flex h-full flex-col rounded-2xl border border-border bg-surface p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium tracking-wide text-muted uppercase">{node.label}</span>
        {Icon && (
          <span className="grid size-7 place-items-center rounded-lg bg-brand/10 text-brand">
            <Icon className="size-4" />
          </span>
        )}
      </div>
      <div className="mt-2 flex items-baseline gap-1.5">
        <span className="text-2xl font-semibold tracking-tight tabular-nums sm:text-3xl">
          {formatValue(node.value)}
        </span>
        {node.unit && <span className="text-sm text-muted">{node.unit}</span>}
      </div>
      <div className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-1 pt-2 text-xs">
        {hasChange && (
          <span
            className={cn(
              'inline-flex items-center gap-0.5 font-medium tabular-nums',
              change === 0 ? 'text-muted' : isGood ? 'text-good' : 'text-bad',
            )}
          >
            <Arrow className="size-3.5" />
            {change > 0 ? '+' : ''}
            {formatValue(change)}%
          </span>
        )}
        {node.caption && <span className="text-muted">{node.caption}</span>}
      </div>
    </div>
  )
}
