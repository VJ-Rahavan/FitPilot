import { clsx, type ClassValue } from 'clsx'

export const cn = (...inputs: ClassValue[]) => clsx(inputs)

export const uid = () => crypto.randomUUID()

const numberFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return numberFormat.format(value)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/** "2026-09-12" → "Sep 12"; anything else unchanged. */
export function formatAxisLabel(value: unknown): string {
  if (typeof value === 'string' && ISO_DATE.test(value)) {
    const date = new Date(`${value}T00:00:00`)
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }
  return formatValue(value)
}

export function relativeTime(iso: string): string {
  // Backend timestamps are UTC; SQLite may drop the offset.
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days}d ago`
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function humanize(action: string): string {
  const text = action.replace(/[_-]+/g, ' ').trim()
  return text.charAt(0).toUpperCase() + text.slice(1)
}
