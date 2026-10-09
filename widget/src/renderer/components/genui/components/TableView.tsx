import { cn, formatValue } from '../../../lib/format'
import type { TableNode } from '../../../types/ui'
import { Panel, PanelHeader } from '../../ui/primitives'

const ALIGN = { left: 'text-left', center: 'text-center', right: 'text-right' } as const

export function TableView({ node }: { node: TableNode }) {
  return (
    <Panel className="p-0! sm:p-0!">
      {node.title && (
        <div className="px-4 pt-4 sm:px-5">
          <PanelHeader title={node.title} />
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-xs tracking-wide text-muted uppercase">
              {node.columns.map((col) => (
                <th
                  key={col.key}
                  className={cn('px-4 py-2.5 font-medium whitespace-nowrap sm:px-5', ALIGN[col.align ?? 'left'])}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {node.rows.map((row, i) => (
              <tr key={i} className="border-b border-border/60 last:border-0 hover:bg-surface-2/60">
                {node.columns.map((col) => (
                  <td
                    key={col.key}
                    className={cn(
                      'px-4 py-2.5 tabular-nums sm:px-5',
                      ALIGN[col.align ?? (typeof row[col.key] === 'number' ? 'right' : 'left')],
                    )}
                  >
                    {formatValue(row[col.key])}
                  </td>
                ))}
              </tr>
            ))}
            {node.rows.length === 0 && (
              <tr>
                <td colSpan={node.columns.length} className="px-5 py-6 text-center text-muted">
                  No rows
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
