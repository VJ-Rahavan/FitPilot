import type { PlateDiagramNode } from '../../../types/ui'
import { Panel, PanelHeader } from '../../ui/primitives'

/** Plates on one side of the bar, heaviest closest to the sleeve stop. */
export function PlateDiagramView({ node }: { node: PlateDiagramNode }) {
  const unit = node.unit ?? 'lb'
  const heaviest = Math.max(...node.plates_per_side, 1)
  return (
    <Panel>
      <PanelHeader
        title={`${node.total_weight} ${unit}`}
        description={`${node.bar_weight} ${unit} bar · each side`}
      />
      <div className="flex items-center gap-1 px-4 pb-4">
        <div className="h-3 w-24 rounded-l bg-border-strong" aria-hidden />
        {node.plates_per_side.map((plate, i) => (
          <div
            key={i}
            className="flex w-9 items-center justify-center rounded bg-brand text-xs font-semibold text-brand-fg"
            style={{ height: `${40 + (plate / heaviest) * 80}px` }}
          >
            {plate}
          </div>
        ))}
        <div className="h-3 w-8 rounded-r bg-border-strong" aria-hidden />
      </div>
      {node.remainder ? (
        <p className="px-4 pb-4 text-sm text-muted">
          {node.remainder} {unit} can't be made with standard plates.
        </p>
      ) : null}
    </Panel>
  )
}
