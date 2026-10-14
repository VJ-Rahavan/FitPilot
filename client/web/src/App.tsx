import { Mic, MicOff, Send, Volume2, VolumeX } from 'lucide-react'
import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { ActionProvider } from './components/genui/ActionContext'
import { UIRenderer } from './components/genui/UIRenderer'
import { type ChatEvent, runAction, streamChat, type ToolResult } from './lib/api'
import { cn } from './lib/format'
import { speak, speechRecognitionSupported, useSpeechRecognition } from './lib/speech'
import type { UIEventInput } from './types/chat'

interface Turn {
  role: 'user' | 'assistant'
  text: string
  tools?: string[]
  error?: boolean
}

const SUGGESTIONS = [
  "What's my workout today?",
  'Start my workout',
  'How was my week?',
  'How is my bench press going?',
  'What plates for 225?',
]

const toolLabel = (name: string) => name.replace(/_/g, ' ')
// "reply" is the agent talking without a FitGen tool: not worth labelling.
const shownTools = (tools: string[]) => tools.filter((t) => t !== 'reply')

export default function App() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [full, setFull] = useState<ToolResult | null>(null)
  const [fragments, setFragments] = useState<ToolResult[]>([])
  const [busy, setBusy] = useState(false)
  const [muted, setMuted] = useState(false)
  const [draft, setDraft] = useState('')
  const conversationId = useRef<string | null>(null)
  const transcriptEnd = useRef<HTMLDivElement>(null)

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [turns, busy])

  const say = useCallback((text: string) => !muted && speak(text), [muted])

  const show = useCallback((result: ToolResult) => {
    if (result.components.length === 0) return // e.g. a greeting: keep what's on screen
    if (result.display === 'full') {
      setFull(result)
      setFragments([])
    } else {
      // Only the newest quick result: older session cards (with live buttons) would invite
      // pressing a stale "Log set".
      setFragments([result])
    }
  }, [])

  const send = useCallback(
    async (text: string) => {
      const message = text.trim()
      if (!message || busy) return
      setBusy(true)
      setTurns((t) => [...t, { role: 'user', text: message }])
      const tools: string[] = []
      let reply = ''
      let failed = false
      await streamChat(message, conversationId.current, (e: ChatEvent) => {
        if (e.event === 'tool_start') tools.push(e.data.name)
        else if (e.event === 'tool_result') show(e.data)
        else if (e.event === 'done') {
          conversationId.current = e.data.conversation_id
          reply = e.data.text
        } else if (e.event === 'error') {
          reply = e.data.message
          failed = true
        }
      }).catch(() => {
        reply = 'I lost the connection. Please try again.'
        failed = true
      })
      setTurns((t) => [...t, { role: 'assistant', text: reply, tools, error: failed }])
      say(reply)
      setBusy(false)
    },
    [busy, say, show],
  )

  const dispatch = useCallback(
    async (event: UIEventInput) => {
      if (busy) return
      setBusy(true)
      setTurns((t) => [...t, { role: 'user', text: event.label ?? toolLabel(event.action) }])
      try {
        const result = await runAction(event.action, event.payload)
        show(result)
        setTurns((t) => [...t, { role: 'assistant', text: result.text, tools: [event.action] }])
        say(result.text)
      } catch {
        setTurns((t) => [...t, { role: 'assistant', text: "That didn't work. Please try again.", error: true }])
      } finally {
        setBusy(false)
      }
    },
    [busy, say, show],
  )

  const mic = useSpeechRecognition((text) => void send(text))
  const micSupported = speechRecognitionSupported()

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    void send(draft)
    setDraft('')
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-border px-6 py-3">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold">
            Fit<span className="text-brand">Gen</span>
          </span>
          <span className="text-sm text-muted">voice coach · demo client for Alexa+</span>
        </div>
        <button
          type="button"
          onClick={() => setMuted((m) => !m)}
          className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-fg"
          aria-label={muted ? 'Unmute replies' : 'Mute replies'}
        >
          {muted ? <VolumeX className="size-5" /> : <Volume2 className="size-5" />}
        </button>
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[380px_1fr]">
        <section className="flex min-h-0 flex-col border-r border-border">
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {turns.length === 0 && (
              <div className="space-y-2">
                <p className="text-sm text-muted">Tap the mic and talk, or try:</p>
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void send(s)}
                    className="block w-full rounded-xl border border-border bg-surface px-3 py-2 text-left text-sm hover:bg-surface-2"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
            {turns.map((turn, i) => (
              <div key={i} className={cn('flex', turn.role === 'user' ? 'justify-end' : 'justify-start')}>
                <div
                  className={cn(
                    'max-w-[85%] rounded-2xl px-3 py-2 text-sm',
                    turn.role === 'user' ? 'bg-brand text-brand-fg' : 'bg-surface-2 text-fg',
                    turn.error && 'border border-bad/40 text-bad',
                  )}
                >
                  {turn.text}
                  {turn.tools && shownTools(turn.tools).length > 0 && (
                    <div className="mt-1 text-xs text-muted">
                      {shownTools(turn.tools).map(toolLabel).join(' · ')}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && <div className="text-sm text-muted animate-pulse">FitGen is thinking…</div>}
            <div ref={transcriptEnd} />
          </div>

          <form onSubmit={onSubmit} className="flex items-center gap-2 border-t border-border p-3">
            <button
              type="button"
              disabled={!micSupported || busy}
              onClick={mic.listening ? mic.stop : mic.start}
              className={cn(
                'flex size-12 shrink-0 items-center justify-center rounded-full transition-colors',
                mic.listening ? 'bg-bad text-white animate-pulse' : 'bg-brand text-brand-fg hover:bg-brand-dim',
                'disabled:cursor-not-allowed disabled:opacity-40',
              )}
              aria-label={mic.listening ? 'Stop listening' : 'Talk'}
              title={micSupported ? 'Push to talk' : 'Voice input needs Chrome or Edge'}
            >
              {micSupported ? <Mic className="size-5" /> : <MicOff className="size-5" />}
            </button>
            <input
              value={mic.listening ? mic.interim : draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={mic.listening ? 'Listening…' : 'Or type, e.g. "only got 6"'}
              disabled={busy || mic.listening}
              className="h-12 min-w-0 flex-1 rounded-xl border border-border bg-surface px-3 text-sm outline-none focus:border-brand"
            />
            <button
              type="submit"
              disabled={busy || !draft.trim()}
              className="flex size-12 items-center justify-center rounded-xl bg-surface-2 text-fg hover:bg-surface-3 disabled:opacity-40"
              aria-label="Send"
            >
              <Send className="size-4" />
            </button>
          </form>
          {mic.error && <p className="px-3 pb-2 text-xs text-bad">{mic.error}</p>}
        </section>

        <section className="min-h-0 overflow-y-auto p-6">
          <ActionProvider dispatch={(e) => void dispatch(e)} disabled={busy}>
            <div className="mx-auto flex max-w-4xl flex-col gap-6">
              {fragments.map((r, i) => (
                <div key={`${r.name}-${i}`} className={cn(i > 0 && 'opacity-60')}>
                  <UIRenderer components={r.components} />
                </div>
              ))}
              {full && <UIRenderer components={full.components} />}
              {!full && fragments.length === 0 && (
                <div className="mt-24 text-center text-muted">
                  Results from FitGen's tools show up here.
                </div>
              )}
            </div>
          </ActionProvider>
        </section>
      </main>
    </div>
  )
}
