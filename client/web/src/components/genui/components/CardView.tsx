import type { CardNode } from '../../../types/ui'
import { NestedPanels, Panel, PanelHeader } from '../../ui/primitives'
import { UINodeView } from '../UIRenderer'

export function CardView({ node }: { node: CardNode }) {
  return (
    <Panel>
      <PanelHeader title={node.title} description={node.description} />
      <NestedPanels>
        <div className="flex flex-col gap-4">
          {node.children?.map((child, i) => <UINodeView key={i} node={child} />)}
        </div>
      </NestedPanels>
    </Panel>
  )
}
