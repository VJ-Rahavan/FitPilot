import { useCallback, useEffect, useRef, useState } from 'react'

/* Web Speech API: recognition in Chrome/Edge (webkit prefix), synthesis in all browsers. */

interface RecognitionResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>
}

interface Recognition {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((e: RecognitionResultEvent) => void) | null
  onend: (() => void) | null
  onerror: ((e: { error: string }) => void) | null
  start(): void
  stop(): void
}

type RecognitionCtor = new () => Recognition

function recognitionCtor(): RecognitionCtor | undefined {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition
}

export const speechRecognitionSupported = () => recognitionCtor() !== undefined

/** Push-to-talk: `start()` listens, and `onFinal` gets the transcript when speech ends. */
export function useSpeechRecognition(onFinal: (text: string) => void) {
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState<string | null>(null)
  const recognition = useRef<Recognition | null>(null)
  const finalRef = useRef(onFinal)
  finalRef.current = onFinal

  const start = useCallback(() => {
    const Ctor = recognitionCtor()
    if (!Ctor || recognition.current) return
    window.speechSynthesis?.cancel() // don't listen to ourselves
    const r = new Ctor()
    r.lang = 'en-US'
    r.interimResults = true
    r.continuous = false
    let finalText = ''
    r.onresult = (e) => {
      let text = ''
      for (let i = 0; i < e.results.length; i++) {
        text += e.results[i][0].transcript
        if (e.results[i].isFinal) finalText = text
      }
      setInterim(text)
    }
    r.onerror = (e) => setError(e.error === 'not-allowed' ? 'Microphone access was blocked.' : null)
    r.onend = () => {
      recognition.current = null
      setListening(false)
      setInterim('')
      if (finalText.trim()) finalRef.current(finalText.trim())
    }
    recognition.current = r
    setError(null)
    setListening(true)
    r.start()
  }, [])

  const stop = useCallback(() => recognition.current?.stop(), [])
  useEffect(() => () => recognition.current?.stop(), [])
  return { listening, interim, error, start, stop }
}

/** Speak `text` aloud, replacing anything still being spoken. */
export function speak(text: string) {
  const synth = window.speechSynthesis
  if (!synth || !text) return
  synth.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'en-US'
  utterance.rate = 1.05
  synth.speak(utterance)
}
