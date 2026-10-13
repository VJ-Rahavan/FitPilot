import { Pause, Play, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { TimerNode } from '../../../types/ui'

const RADIUS = 52
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

function beep() {
  try {
    const ctx = new AudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.frequency.value = 880
    gain.gain.setValueAtTime(0.2, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6)
    osc.connect(gain).connect(ctx.destination)
    osc.start()
    osc.stop(ctx.currentTime + 0.6)
    osc.onended = () => void ctx.close()
  } catch {
    /* audio unavailable */
  }
}

const mmss = (s: number) =>
  `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

export function TimerView({ node }: { node: TimerNode }) {
  const total = node.seconds
  const [remaining, setRemaining] = useState(total)
  const [running, setRunning] = useState(false)
  const endAt = useRef<number | null>(null)

  useEffect(() => {
    if (!running) return
    endAt.current = Date.now() + remaining * 1000
    const id = window.setInterval(() => {
      const left = Math.max(0, ((endAt.current ?? 0) - Date.now()) / 1000)
      setRemaining(left)
      if (left <= 0) {
        setRunning(false)
        beep()
      }
    }, 200)
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restart only on run toggle
  }, [running])

  const done = remaining <= 0
  const progress = remaining / total

  return (
    <div className="flex items-center gap-5 rounded-2xl border border-border bg-surface p-4">
      <div className="relative size-28 shrink-0">
        <svg viewBox="0 0 120 120" className="size-full -rotate-90">
          <circle cx="60" cy="60" r={RADIUS} fill="none" stroke="var(--color-surface-3)" strokeWidth="8" />
          <circle
            cx="60"
            cy="60"
            r={RADIUS}
            fill="none"
            stroke={done ? 'var(--color-good)' : 'var(--color-brand)'}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - progress)}
            className="transition-[stroke-dashoffset] duration-200 ease-linear"
          />
        </svg>
        <span className="absolute inset-0 grid place-items-center font-mono text-xl font-semibold tabular-nums">
          {done ? 'Go!' : mmss(Math.ceil(remaining))}
        </span>
      </div>
      <div className="min-w-0">
        <p className="font-semibold">{node.label ?? 'Timer'}</p>
        <p className="text-sm text-muted">{mmss(total)} total</p>
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => (done ? (setRemaining(total), setRunning(true)) : setRunning((r) => !r))}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand px-3.5 text-sm font-semibold text-brand-fg hover:bg-brand-dim"
          >
            {running ? <Pause className="size-4" /> : <Play className="size-4" />}
            {running ? 'Pause' : done ? 'Restart' : remaining < total ? 'Resume' : 'Start'}
          </button>
          <button
            type="button"
            aria-label="Reset timer"
            onClick={() => {
              setRunning(false)
              setRemaining(total)
            }}
            className="grid size-9 place-items-center rounded-lg border border-border-strong text-muted hover:bg-surface-2 hover:text-fg"
          >
            <RotateCcw className="size-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
