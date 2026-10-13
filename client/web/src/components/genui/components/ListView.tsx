import type { ListNode } from '../../../types/ui'
import { Badge, Panel, PanelHeader } from '../../ui/primitives'

export function ListView({ node }: { node: ListNode }) {
  return (
    <Panel>
      <PanelHeader title={node.title} />
      <ul className="flex flex-col divide-y divide-border/70">
        {node.items.map((item, i) => (
          <li key={i} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
            <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-brand/10 text-xs font-semibold text-brand">
              {node.ordered ? i + 1 : '•'}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{item.title}</span>
                {item.badge && <Badge tone="brand">{item.badge}</Badge>}
              </div>
              {item.description && <p className="mt-0.5 text-sm text-muted">{item.description}</p>}
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  )
}
