import { Check } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { cn } from '../../../lib/format'
import type { FormFieldSpec, FormNode, Scalar } from '../../../types/ui'
import { Panel, PanelHeader } from '../../ui/primitives'
import { useUIAction } from '../useUIAction'

type Values = Record<string, Scalar>

const inputClass =
  'w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-fg placeholder:text-subtle ' +
  'outline-none transition-colors focus:border-brand/60 focus:ring-2 focus:ring-brand/15 disabled:opacity-60'

function initialValues(fields: FormFieldSpec[]): Values {
  return Object.fromEntries(
    fields.map((f) => {
      if (f.default !== undefined && f.default !== null) return [f.name, f.default]
      if (f.input === 'checkbox') return [f.name, false]
      if (f.input === 'select' && f.options?.length && f.required) return [f.name, f.options[0].value]
      return [f.name, '']
    }),
  )
}

/** Drop empty optional values and coerce numbers so the agent gets clean, typed data. */
function toPayload(fields: FormFieldSpec[], values: Values): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  for (const f of fields) {
    const value = values[f.name]
    if (value === '' || value === null || value === undefined) continue
    payload[f.name] = f.input === 'number' ? Number(value) : value
  }
  return payload
}

export function FormView({ node }: { node: FormNode }) {
  const { dispatch, disabled } = useUIAction()
  const [values, setValues] = useState<Values>(() => initialValues(node.fields))
  const [submitted, setSubmitted] = useState(false)
  const locked = disabled || submitted

  const set = (name: string, value: Scalar) => setValues((v) => ({ ...v, [name]: value }))

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (locked) return
    setSubmitted(true)
    dispatch({
      action: node.action,
      payload: toPayload(node.fields, values),
      label: node.title ? `${node.submit_label ?? 'Submit'} · ${node.title}` : node.submit_label,
    })
  }

  return (
    <Panel>
      <PanelHeader title={node.title} description={node.description} />
      <form onSubmit={onSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {node.fields.map((field) => (
          <Field
            key={field.name}
            field={field}
            value={values[field.name]}
            onChange={(v) => set(field.name, v)}
            disabled={locked}
          />
        ))}
        <div className="flex items-center gap-3 sm:col-span-2">
          <button
            type="submit"
            disabled={locked}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-5 text-sm font-semibold text-brand-fg transition-colors hover:bg-brand-dim disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitted && <Check className="size-4" />}
            {submitted ? 'Submitted' : (node.submit_label ?? 'Submit')}
          </button>
        </div>
      </form>
    </Panel>
  )
}

function Field({
  field,
  value,
  onChange,
  disabled,
}: {
  field: FormFieldSpec
  value: Scalar
  onChange: (value: Scalar) => void
  disabled: boolean
}) {
  const id = `field-${field.name}`
  const wide = field.input === 'textarea'

  if (field.input === 'checkbox') {
    return (
      <label htmlFor={id} className="flex cursor-pointer items-center gap-2.5 text-sm sm:col-span-2">
        <input
          id={id}
          type="checkbox"
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          className="size-4 rounded accent-brand"
        />
        {field.label}
      </label>
    )
  }

  let control
  if (field.input === 'select') {
    // Options may carry numeric values: select by index to preserve the original type.
    const options = field.options ?? []
    const index = options.findIndex((o) => o.value === value)
    control = (
      <select
        id={id}
        required={field.required}
        disabled={disabled}
        value={index === -1 ? '' : String(index)}
        onChange={(e) => onChange(e.target.value === '' ? '' : options[Number(e.target.value)].value)}
        className={inputClass}
      >
        {!field.required && <option value="">—</option>}
        {field.required && index === -1 && (
          <option value="" disabled>
            Select…
          </option>
        )}
        {options.map((o, i) => (
          <option key={i} value={i}>
            {o.label}
          </option>
        ))}
      </select>
    )
  } else if (field.input === 'textarea') {
    control = (
      <textarea
        id={id}
        rows={3}
        required={field.required}
        disabled={disabled}
        placeholder={field.placeholder}
        value={String(value ?? '')}
        onChange={(e) => onChange(e.target.value)}
        className={cn(inputClass, 'resize-y')}
      />
    )
  } else {
    control = (
      <div className="relative">
        <input
          id={id}
          type={field.input ?? 'text'}
          required={field.required}
          disabled={disabled}
          placeholder={field.placeholder}
          min={field.min}
          max={field.max}
          step={field.step ?? (field.input === 'number' ? 'any' : undefined)}
          value={String(value ?? '')}
          onChange={(e) => onChange(e.target.value)}
          className={cn(inputClass, field.unit && 'pr-12')}
        />
        {field.unit && (
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-muted">
            {field.unit}
          </span>
        )}
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col gap-1.5', wide && 'sm:col-span-2')}>
      <label htmlFor={id} className="text-xs font-medium text-muted">
        {field.label}
        {field.required && <span className="text-brand"> *</span>}
      </label>
      {control}
    </div>
  )
}
