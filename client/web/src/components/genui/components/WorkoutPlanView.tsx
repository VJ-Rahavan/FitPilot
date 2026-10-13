import { CalendarDays, Target } from 'lucide-react'
import { useState } from 'react'
import { cn } from '../../../lib/format'
import type { WorkoutPlanNode } from '../../../types/ui'
import { Badge, Panel } from '../../ui/primitives'

function formatRest(seconds?: number) {
  if (!seconds) return '—'
  return seconds >= 60 && seconds % 60 === 0 ? `${seconds / 60} min` : `${seconds}s`
}

export function WorkoutPlanView({ node }: { node: WorkoutPlanNode }) {
  const [active, setActive] = useState(0)
  const day = node.days[Math.min(active, node.days.length - 1)]
  const totalSets = day.exercises.reduce((sum, e) => sum + e.sets, 0)

  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold tracking-tight">{node.title}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
            {node.goal && (
              <span className="inline-flex items-center gap-1">
                <Target className="size-3.5" /> {node.goal}
              </span>
            )}
            <span className="inline-flex items-center gap-1">
              <CalendarDays className="size-3.5" /> {node.days.length} days/week
              {node.weeks ? ` · ${node.weeks} weeks` : ''}
            </span>
          </div>
        </div>
      </div>

      <div className="mt-4 flex gap-1.5 overflow-x-auto pb-1" role="tablist">
        {node.days.map((d, i) => (
          <button
            key={i}
            role="tab"
            aria-selected={i === active}
            onClick={() => setActive(i)}
            className={cn(
              'shrink-0 rounded-lg px-3 py-1.5 text-left text-sm transition-colors',
              i === active
                ? 'bg-brand text-brand-fg'
                : 'bg-surface-2 text-muted hover:bg-surface-3 hover:text-fg',
            )}
          >
            <span className="block font-semibold">{d.day}</span>
            <span className={cn('block text-xs', i === active ? 'text-brand-fg/70' : 'text-subtle')}>
              {d.focus}
            </span>
          </button>
        ))}
      </div>

      <div className="mt-4 flex items-center justify-between">
        <p className="text-sm font-medium">{day.focus}</p>
        <Badge>{totalSets} sets</Badge>
      </div>
      <ul className="mt-2 flex flex-col divide-y divide-border/70 rounded-xl border border-border">
        {day.exercises.map((ex, i) => (
          <li key={i} className="flex items-center gap-3 px-3.5 py-3">
            <span className="w-5 text-xs font-semibold text-subtle tabular-nums">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{ex.name}</p>
              {ex.notes && <p className="truncate text-xs text-muted">{ex.notes}</p>}
            </div>
            <div className="text-right">
              <p className="text-sm font-semibold tabular-nums">
                {ex.sets} × {ex.reps}
              </p>
              <p className="text-xs text-muted tabular-nums">rest {formatRest(ex.rest_seconds)}</p>
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  )
}
