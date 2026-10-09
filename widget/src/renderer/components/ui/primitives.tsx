import { createContext, useContext, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '../../lib/format'

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn('md', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{ a: (props) => <a {...props} target="_blank" rel="noreferrer" /> }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}

const NestedContext = createContext(false)

/** Marks its subtree as inside a panel, so inner panels render flat instead of box-in-box. */
export function NestedPanels({ children }: { children: ReactNode }) {
  return <NestedContext.Provider value={true}>{children}</NestedContext.Provider>
}

export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  const nested = useContext(NestedContext)
  if (nested) return <div>{children}</div>
  return (
    <div className={cn('rounded-2xl border border-border bg-surface p-4 sm:p-5', className)}>
      {children}
    </div>
  )
}

export function PanelHeader({ title, description }: { title?: string; description?: string }) {
  if (!title && !description) return null
  return (
    <div className="mb-4">
      {title && <h3 className="text-[15px] font-semibold tracking-tight">{title}</h3>}
      {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
    </div>
  )
}

const BADGE_TONES = {
  neutral: 'bg-surface-3 text-muted',
  brand: 'bg-brand/15 text-brand',
  good: 'bg-good/15 text-good',
  warn: 'bg-warn/15 text-warn',
  bad: 'bg-bad/15 text-bad',
} as const

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: keyof typeof BADGE_TONES
  children: ReactNode
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        BADGE_TONES[tone],
      )}
    >
      {children}
    </span>
  )
}
