import type { TextNode } from '../../../types/ui'
import { Markdown } from '../../ui/primitives'

/** Headings are plain text; models sometimes include markdown markers anyway. */
const plain = (text: string) => text.replace(/^#+\s*/, '').replace(/\*\*(.+?)\*\*/g, '$1')

export function TextView({ node }: { node: TextNode }) {
  switch (node.variant) {
    case 'heading':
      return (
        <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">{plain(node.content)}</h2>
      )
    case 'subheading':
      return (
        <h3 className="text-base font-semibold tracking-tight text-fg/90">{plain(node.content)}</h3>
      )
    case 'muted':
      return <Markdown className="text-sm! text-muted!">{node.content}</Markdown>
    default:
      return <Markdown>{node.content}</Markdown>
  }
}
