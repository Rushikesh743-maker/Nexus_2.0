import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Send, Bot, ArrowUpRight, Sparkles } from 'lucide-react';
import { Drawer } from '@/components/modals/Drawer';
import { Input } from '@/components/ui/Input';
import { Logo } from '@/components/ui/Logo';
import { Spinner } from '@/components/ui/LoadingState';
import { analysisService } from '@/services';
import { cn } from '@/lib/utils';
import { Button } from '../ui/Button';

const SUGGESTIONS = [
  'Why are the top two entities connected?',
  'What evidence contradicts this relationship?',
  'What changed after new evidence?',
  'What information is missing?',
];

/**
 * NEXUS Copilot — right-side assistant panel (mock).
 * Responses come from analysisService.askCopilot(); swapping that single
 * function for a streaming backend API (SSE/WebSocket) requires no UI
 * changes. Responses always include sources or deep links where relevant.
 */
export function CopilotDrawer({ open, onClose, investigationId }) {
  const navigate = useNavigate();
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [thinking, setThinking] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (open && messages.length === 0) {
      setMessages([
        {
          role: 'assistant',
          text: 'Hello — I am the NEXUS copilot for this investigation. Ask about connections, contradictions, recent changes or missing information. I can only explain what is recorded in the case.',
        },
      ]);
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, thinking]);

  const ask = async (text) => {
    const q = String(text).trim();
    if (!q || thinking) return;
    setQuestion('');
    setMessages((m) => [...m, { role: 'user', text: q }]);
    setThinking(true);
    try {
      const reply = await analysisService.askCopilot(investigationId, q);
      setMessages((m) => [...m, { role: 'assistant', text: reply.answer, links: reply.links || [] }]);
    } catch {
      setMessages((m) => [...m, { role: 'assistant', text: 'I could not reach the analysis service. This demo runs on mock responses — try again.', links: [] }]);
    } finally {
      setThinking(false);
    }
  };

  return (
    <Drawer open={open} onClose={onClose} width={420} title="NEXUS Copilot" subtitle="Investigation assistant · mock responses">
      <div className="flex h-full flex-col">
        <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1 scrollbar-thin">
          {messages.map((m, i) => (
            <div key={i} className={cn('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
              <div
                className={cn(
                  'max-w-[92%] rounded-xl px-3.5 py-2.5 text-[13px] leading-relaxed',
                  m.role === 'user' ? 'bg-teal-600 text-white' : 'border border-slate-200 bg-white text-navy-700'
                )}
              >
                {m.role === 'assistant' && (
                  <span className="mb-1 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-teal-700">
                    <Sparkles className="h-3 w-3" aria-hidden /> NEXUS
                  </span>
                )}
                {m.text}
                {m.links?.length > 0 && (
                  <span className="mt-2 flex flex-wrap gap-1.5">
                    {m.links.map((link) => (
                      <button
                        key={link.to}
                        type="button"
                        onClick={() => {
                          onClose();
                          navigate(link.to);
                        }}
                        className="inline-flex items-center gap-1 rounded-lg border border-teal-200 bg-teal-50 px-2 py-1 text-[11.5px] font-medium text-teal-800 transition-colors hover:bg-teal-100"
                      >
                        {link.label}
                        <ArrowUpRight className="h-3 w-3" aria-hidden />
                      </button>
                    ))}
                  </span>
                )}
              </div>
            </div>
          ))}
          {thinking && (
            <div className="flex items-center gap-2 text-[12px] text-navy-300">
              <Spinner className="h-3.5 w-3.5" /> NEXUS is reviewing the case record…
            </div>
          )}
        </div>

        <div className="border-t border-slate-100 pt-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-navy-300">Suggested questions</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => ask(s)}
                disabled={thinking}
                className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-navy-500 transition-colors hover:border-teal-300 hover:text-teal-800 disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
          <form
            className="mt-3 flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              ask(question);
            }}
          >
            <Input
              placeholder="Ask about this investigation…"
              aria-label="Ask the NEXUS copilot"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
            <Button type="submit" size="icon" aria-label="Send question" disabled={thinking || !question.trim()}>
              <Send className="h-4 w-4" aria-hidden />
            </Button>
          </form>
          <p className="mt-2 text-[10.5px] leading-relaxed text-navy-300">
            Mock assistant for the frontend build — responses cite recorded data only. NEXUS provides analytical assistance and
            investigation leads; it does not determine guilt or replace investigator judgment.
          </p>
        </div>
      </div>
    </Drawer>
  );
}
