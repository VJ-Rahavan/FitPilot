import { cn } from '../../../lib/format'
import type { LayoutNode } from '../../../types/ui'
import { UINodeView } from '../UIRenderer'

// Static class names so Tailwind can see them.
const GRID_COLUMNS: Record<number, string> = {
  1: 'grid-cols-1',
  2: 'grid-cols-1 sm:grid-cols-2',
  3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
  4: 'grid-cols-2 lg:grid-cols-4',
}

export function LayoutView({ node }: { node: LayoutNode }) {
  const direction = node.direction ?? 'column'
  const allButtons = node.children.every((c) => c.type === 'button')

  const className =
    direction === 'grid'
      ? cn('grid gap-3', GRID_COLUMNS[Math.min(Math.max(node.columns ?? 2, 1), 4)])
      : direction === 'row'
        ? cn('flex flex-wrap gap-3', !allButtons && '*:min-w-[180px] *:flex-1')
        : 'flex flex-col gap-4'

  return (
    <div className={className}>
      {node.children.map((child, i) => (
        <UINodeView key={i} node={child} />
      ))}
    </div>
  )
}
