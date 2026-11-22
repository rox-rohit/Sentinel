import { ArrowUpRight, Send, Sparkles, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { useData } from '../../lib/data-context'
import { askAssistant, ASSISTANT_SUGGESTIONS, type AssistantReply } from '../../lib/assistant'
import { cx } from '../../lib/cx'
import { navigate } from '../../lib/router'

interface Message {
  id: number
  role: 'user' | 'assistant'
  text: string
  reply?: AssistantReply
}

let nextId = 1

function ReplyBody({ reply, onNavigate }: { reply: AssistantReply; onNavigate: (href: string) => void }) {
  return (
    <div className="space-y-2">
      <p className="text-[11.5px] leading-relaxed text-fg">{reply.text}</p>
      {reply.bullets.length > 0 && (
        <ul className="space-y-1">
          {reply.bullets.map((bullet, index) => (
            <li key={index} className="flex gap-1.5 text-[11px] leading-relaxed text-muted">
              <span className="mt-[7px] size-1 shrink-0 rounded-full bg-[var(--color-accent)]" />
              <span>{bullet}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        {reply.links.map((link) => (
          <button
            key={link.href}
            onClick={() => onNavigate(link.href)}
            className="inline-flex items-center gap-1 rounded-full border border-[var(--color-line)] px-2 py-[3px] text-[10px] text-[var(--color-accent)] transition-colors hover:border-[var(--accent-line)]"
          >
            {link.label} <ArrowUpRight className="size-2.5" />
          </button>
        ))}
      </div>
      <p className="text-[9.5px] uppercase tracking-[0.08em] text-faint">{reply.source}</p>
    </div>
  )
}

export function AssistantDock() {
  const { data, source } = useData()
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([
    {
      id: nextId++,
      role: 'assistant',
      text: '',
      reply: askAssistant('', data),
    },
  ])
  const scroller = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const element = scroller.current
    if (element) element.scrollTop = element.scrollHeight
  }, [messages, open])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const send = (question: string) => {
    const text = question.trim()
    if (!text) return
    const reply = askAssistant(text, data)
    setMessages((current) => [
      ...current,
      { id: nextId++, role: 'user', text },
      { id: nextId++, role: 'assistant', text: '', reply },
    ])
    setInput('')
  }

  const go = (href: string) => {
    navigate(href)
    setOpen(false)
  }

  return (
    <>
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="Ask SENTINEL"
          className="fixed bottom-4 right-4 z-40 inline-flex items-center gap-2 rounded-full border border-[var(--accent-line)] bg-[var(--color-surface)] px-3.5 py-2.5 text-[11.5px] font-medium text-fg shadow-[0_10px_30px_-12px_rgba(0,0,0,0.6)] transition-transform hover:-translate-y-0.5"
        >
          <Sparkles className="size-3.5 text-[var(--color-accent)]" />
          Ask SENTINEL
          <span className="hidden text-[9px] uppercase tracking-[0.08em] text-faint sm:inline">
            {source === 'live' ? 'live' : 'snapshot'}
          </span>
        </button>
      )}

      {open && (
        <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[400px] flex-col border-l border-[var(--color-line)] bg-[var(--color-bg-deep)] shadow-[-20px_0_60px_-30px_rgba(0,0,0,0.8)]">
          <header className="flex items-center gap-2 border-b border-[var(--color-line)] px-4 py-3">
            <div className="grid size-7 place-items-center rounded-[8px] border border-[var(--accent-line)] bg-[var(--accent-soft)]">
              <Sparkles className="size-3.5 text-[var(--color-accent)]" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[12px] font-medium">SENTINEL assistant</div>
              <div className="text-[9.5px] uppercase tracking-[0.1em] text-faint">
                Answers from build {data.meta.build_version} · {source === 'live' ? 'live API' : 'snapshot'}
              </div>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Close assistant"
              className="rounded-[6px] p-1 text-faint hover:text-fg">
              <X className="size-4" />
            </button>
          </header>

          <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto px-3 py-3">
            {messages.map((message) => (
              <div key={message.id} className={cx('flex', message.role === 'user' ? 'justify-end' : 'justify-start')}>
                {message.role === 'user' ? (
                  <p className="max-w-[85%] rounded-[10px] rounded-br-[3px] bg-[var(--accent-soft)] px-3 py-2 text-[11.5px] leading-relaxed text-fg">
                    {message.text}
                  </p>
                ) : (
                  <div className="w-full rounded-[10px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-3 py-2.5">
                    {message.reply && <ReplyBody reply={message.reply} onNavigate={go} />}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="border-t border-[var(--color-line)] px-3 py-2.5">
            <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1">
              {ASSISTANT_SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => send(suggestion)}
                  className="shrink-0 rounded-full border border-[var(--color-line)] px-2 py-1 text-[10px] text-muted transition-colors hover:border-[var(--accent-line)] hover:text-fg"
                >
                  {suggestion}
                </button>
              ))}
            </div>
            <form
              onSubmit={(event) => { event.preventDefault(); send(input) }}
              className="flex items-end gap-2"
            >
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    send(input)
                  }
                }}
                rows={1}
                placeholder="Ask about the fleet, an asset, alerts, models…"
                className="max-h-28 min-h-[36px] flex-1 resize-none rounded-[8px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-2.5 py-2 text-[11.5px] outline-none placeholder:text-faint focus:border-[var(--accent-line)]"
              />
              <button
                type="submit"
                disabled={!input.trim()}
                aria-label="Send question"
                className="grid size-9 place-items-center rounded-[8px] border border-[var(--accent-line)] bg-[var(--accent-soft)] text-[var(--color-accent)] disabled:opacity-40"
              >
                <Send className="size-3.5" />
              </button>
            </form>
            <p className="mt-1.5 text-[9.5px] leading-relaxed text-faint">
              Retrieval over the loaded platform payload. Model attribution is not physical causation.
            </p>
          </div>
        </div>
      )}
    </>
  )
}
