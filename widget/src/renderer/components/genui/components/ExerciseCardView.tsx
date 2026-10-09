import { Dumbbell, Lightbulb } from 'lucide-react'
import type { ExerciseCardNode } from '../../../types/ui'
import { Badge, Panel } from '../../ui/primitives'

const DIFFICULTY_TONE = { beginner: 'good', intermediate: 'warn', advanced: 'bad' } as const

export function ExerciseCardView({ node }: { node: ExerciseCardNode }) {
  return (
    <Panel>
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand/10 text-brand">
          <Dumbbell className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold tracking-tight">{node.name}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {node.difficulty && (
              <Badge tone={DIFFICULTY_TONE[node.difficulty]}>{node.difficulty}</Badge>
            )}
            {node.equipment && <Badge>{node.equipment}</Badge>}
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {node.primary_muscles.map((m) => (
          <Badge key={m} tone="brand">
            {m}
          </Badge>
        ))}
        {node.secondary_muscles?.map((m) => <Badge key={m}>{m}</Badge>)}
      </div>

      <ol className="mt-5 flex flex-col gap-3">
        {node.instructions.map((step, i) => (
          <li key={i} className="flex gap-3 text-sm">
            <span className="grid size-6 shrink-0 place-items-center rounded-full border border-border-strong text-xs font-semibold text-muted">
              {i + 1}
            </span>
            <span className="pt-0.5 leading-relaxed">{step}</span>
          </li>
        ))}
      </ol>

      {node.tips && node.tips.length > 0 && (
        <div className="mt-5 rounded-xl bg-surface-2 p-3.5">
          <p className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-warn uppercase">
            <Lightbulb className="size-3.5" /> Coaching tips
          </p>
          <ul className="mt-2 flex flex-col gap-1.5 text-sm text-fg/85">
            {node.tips.map((tip, i) => (
              <li key={i}>• {tip}</li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  )
}
