import { Dumbbell, Lightbulb } from 'lucide-react'
import type { SessionCardNode } from '../../../types/ui'
import { Panel } from '../../ui/primitives'

/** The current step of a guided workout: big enough to read from across the gym. */
export function SessionCardView({ node }: { node: SessionCardNode }) {
  const weight =
    node.target_weight != null ? `${node.target_weight} ${node.unit ?? 'lb'}` : 'Bodyweight'
  return (
    <Panel className="p-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-sm font-medium tracking-wide text-muted uppercase">
          <Dumbbell className="size-4" /> Set {node.set_number} of {node.total_sets}
        </div>
        {node.next_up && <div className="text-sm text-muted">Next: {node.next_up}</div>}
      </div>
      <div className="mt-3 text-3xl font-semibold text-fg">{node.exercise}</div>
      <div className="mt-4 flex items-baseline gap-6">
        <div>
          <div className="text-5xl font-bold text-brand tabular-nums">{node.target_reps}</div>
          <div className="text-sm text-muted">reps</div>
        </div>
        <div>
          <div className="text-5xl font-bold text-fg tabular-nums">{weight}</div>
          <div className="text-sm text-muted">target</div>
        </div>
      </div>
      {node.form_cue && (
        <div className="mt-5 flex items-start gap-2 rounded-xl bg-surface-2 p-3 text-sm text-fg">
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-warn" /> {node.form_cue}
        </div>
      )}
    </Panel>
  )
}
