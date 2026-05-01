"use client";

import { ArrowUp, Moon, Sparkles, Sun } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";

import { streamAgent } from "@/lib/scout";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";
import { AgnoLogo } from "./ui/agno-logo";
import { Button } from "./ui/button";
import { Markdown } from "./Markdown";

type Msg = {
  id: string;
  role: "user" | "assistant" | "error";
  text: string;
  status?: string; // "thinking…", "calling query_gmail…", etc.
};

const QUICK_PROMPTS = [
  "What should I focus on this week?",
  "Summarize my unread emails from today.",
  "Any meetings I should prepare for?",
  "Which contexts are you connected to?",
];

export function ChatPanel() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const { theme, toggle } = useTheme();

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, busy]);

  // Auto-grow textarea up to a sensible cap.
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, [input]);

  // Cancel any in-flight stream on unmount.
  useEffect(() => () => abortRef.current?.abort(), []);

  async function send(text: string) {
    if (!text.trim() || busy) return;
    const userMsg: Msg = {
      id: crypto.randomUUID(),
      role: "user",
      text: text.trim(),
    };
    const assistantId = crypto.randomUUID();
    const assistantMsg: Msg = {
      id: assistantId,
      role: "assistant",
      text: "",
      status: "thinking…",
    };

    setMessages((m) => [...m, userMsg, assistantMsg]);
    setInput("");
    setBusy(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    function patch(updater: (m: Msg) => Msg) {
      setMessages((prev) =>
        prev.map((msg) => (msg.id === assistantId ? updater(msg) : msg)),
      );
    }

    try {
      await streamAgent(
        text.trim(),
        sessionId,
        (e) => {
          switch (e.kind) {
            case "started":
              if (e.sessionId && !sessionId) setSessionId(e.sessionId);
              break;
            case "tool_started":
              patch((m) => ({ ...m, status: `calling ${e.name}…` }));
              break;
            case "tool_completed":
              patch((m) => ({
                ...m,
                status: m.text ? undefined : "thinking…",
              }));
              break;
            case "content":
              patch((m) => ({
                ...m,
                text: m.text + e.delta,
                status: undefined,
              }));
              break;
            case "completed":
              patch((m) => ({
                ...m,
                status: undefined,
                text: m.text || "_(empty response)_",
              }));
              break;
            case "error":
              patch((m) => ({
                ...m,
                role: "error",
                text: e.message,
                status: undefined,
              }));
              break;
          }
        },
        ctrl.signal,
      );
    } catch (err) {
      patch((m) => ({
        ...m,
        role: "error",
        text: String((err as Error).message || err),
        status: undefined,
      }));
    } finally {
      setBusy(false);
      if (abortRef.current === ctrl) abortRef.current = null;
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send(input);
  }

  return (
    <div className="flex h-full min-w-0 flex-col border-r border-border bg-accent/30 dark:bg-accent/10">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-background px-3">
        <div className="flex items-center gap-2">
          <AgnoLogo className="h-6 w-6 text-agno" />
          <div className="leading-tight">
            <div className="text-sm font-semibold">Scout</div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              company intelligence
            </div>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={toggle}
          aria-label="Toggle theme"
          title="Toggle theme"
          className="h-9 w-9"
          suppressHydrationWarning
        >
          {theme === null ? (
            <span className="inline-block h-4 w-4" />
          ) : (
            <span className="relative inline-flex h-4 w-4">
              <Sun
                className={cn(
                  "absolute inset-0 h-4 w-4 transition-all duration-200",
                  theme === "dark"
                    ? "scale-100 opacity-100"
                    : "scale-50 opacity-0",
                )}
              />
              <Moon
                className={cn(
                  "absolute inset-0 h-4 w-4 transition-all duration-200",
                  theme === "light"
                    ? "scale-100 opacity-100"
                    : "scale-50 opacity-0",
                )}
              />
            </span>
          )}
        </Button>
      </header>

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <EmptyState onPick={send} />
        ) : (
          messages.map((m) => <MessageRow key={m.id} msg={m} />)
        )}
      </div>

      <form
        onSubmit={onSubmit}
        className="shrink-0 border-t border-border bg-background p-3"
      >
        <div className="relative rounded-xl border border-border bg-card transition-[border-color,box-shadow] focus-within:border-foreground/30 focus-within:shadow-[0_0_0_1px_hsl(var(--foreground)/0.05)]">
          <textarea
            ref={taRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            rows={1}
            placeholder="Ask Scout anything…"
            disabled={busy}
            className="block w-full resize-none rounded-xl bg-transparent px-3.5 pb-10 pt-3 text-sm leading-relaxed outline-none placeholder:text-muted-foreground disabled:opacity-50"
          />
          <div className="absolute inset-x-2 bottom-2 flex items-center justify-end">
            <Button
              type="submit"
              variant="agno"
              size="icon"
              disabled={busy || !input.trim()}
              aria-label="Send message"
              className="h-7 w-7 rounded-md"
            >
              <ArrowUp className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="flex h-full flex-col items-start justify-end gap-4 pb-2">
      <div className="rounded-xl border border-border bg-card p-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Sparkles className="h-4 w-4 text-agno" />
          Hi — I'm Scout.
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
          I read across your calendar, email, follow-ups, and the web. Ask me
          anything — or use the briefing on the right as a starting point.
        </p>
      </div>
      <div>
        <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          try
        </div>
        <div className="flex flex-wrap gap-1.5">
          {QUICK_PROMPTS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => onPick(p)}
              className="rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-foreground transition hover:border-foreground/30 hover:bg-accent"
            >
              {p}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function MessageRow({ msg }: { msg: Msg }) {
  if (msg.role === "user") {
    return (
      <div className="flex w-full justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-xl border border-border bg-card px-3.5 py-2 text-sm leading-relaxed text-foreground">
          {msg.text}
        </div>
      </div>
    );
  }
  if (msg.role === "error") {
    return (
      <div className="rounded-md border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-600 dark:text-rose-400">
        {msg.text}
      </div>
    );
  }
  return (
    <div className="flex w-full items-start gap-3">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center text-agno">
        <Sparkles className={cn("h-3.5 w-3.5", msg.status && "animate-pulse")} />
      </div>
      <div className="min-w-0 flex-1 pt-0.5">
        {msg.text ? <Markdown>{msg.text}</Markdown> : null}
        {msg.status && (
          <div className="mt-1 text-xs text-muted-foreground">{msg.status}</div>
        )}
      </div>
    </div>
  );
}
