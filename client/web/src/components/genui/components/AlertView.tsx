import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import { cn } from '../../../lib/format'
import type { AlertNode } from '../../../types/ui'

const VARIANTS = {
  info: { icon: Info, className: 'border-info/30 bg-info/10 text-info' },
  success: { icon: CheckCircle2, className: 'border-good/30 bg-good/10 text-good' },
  warning: { icon: AlertTriangle, className: 'border-warn/30 bg-warn/10 text-warn' },
  error: { icon: XCircle, className: 'border-bad/30 bg-bad/10 text-bad' },
} as const

export function AlertView({ node }: { node: AlertNode }) {
  const { icon: Icon, className } = VARIANTS[node.variant ?? 'info']
  return (
    <div className={cn('flex gap-3 rounded-xl border px-4 py-3', className)} role="status">
      <Icon className="mt-0.5 size-4 shrink-0" />
      <div className="text-sm">
        {node.title && <p className="font-semibold">{node.title}</p>}
        <p className="text-fg/85">{node.message}</p>
      </div>
    </div>
  )
}
