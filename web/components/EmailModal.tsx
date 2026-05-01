"use client";

import {
  ExternalLink,
  Loader2,
  Mail,
  MailOpen,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  EmailMessage,
  EmailThread,
  fetchEmailThread,
  markEmail,
} from "@/lib/scout";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";

function parseFrom(raw: string | null): { name: string; email: string } {
  if (!raw) return { name: "(unknown)", email: "" };
  const m = raw.match(/^\s*"?([^"<]+?)"?\s*<([^>]+)>\s*$/);
  if (m) return { name: m[1].trim(), email: m[2].trim() };
  if (raw.includes("@")) return { name: raw.split("@")[0], email: raw };
  return { name: raw, email: "" };
}

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function EmailModal({
  threadId,
  initialUnread,
  onClose,
  onMarked,
}: {
  threadId: string;
  initialUnread: boolean;
  onClose: () => void;
  onMarked?: (messageId: string, action: "read" | "unread") => void;
}) {
  const [thread, setThread] = useState<EmailThread | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [marking, setMarking] = useState(false);

  // Close on Esc.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    setThread(null);
    setError(null);
    fetchEmailThread(threadId)
      .then((t) => {
        if (!cancelled) setThread(t);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err.message || err));
      });
    return () => {
      cancelled = true;
    };
  }, [threadId]);

  // Compute current unread state from the latest fetched thread (the
  // newest message in the thread is what the briefing card showed).
  const latestMessage = thread?.messages?.[thread.messages.length - 1];
  const isUnread = latestMessage?.is_unread ?? initialUnread;

  async function toggleRead() {
    if (!latestMessage) return;
    const action: "read" | "unread" = isUnread ? "read" : "unread";
    setMarking(true);
    try {
      await markEmail(latestMessage.id, action);
      // Optimistic flip in modal — refetching would just stutter.
      if (thread) {
        setThread({
          ...thread,
          messages: thread.messages.map((m, i) =>
            i === thread.messages.length - 1
              ? { ...m, is_unread: action === "unread" }
              : m,
          ),
        });
      }
      onMarked?.(latestMessage.id, action);
    } catch (err) {
      setError(String((err as Error).message || err));
    } finally {
      setMarking(false);
    }
  }

  const subject = thread?.messages?.[0]?.subject || "(no subject)";
  const gmailUrl = latestMessage
    ? `https://mail.google.com/mail/u/0/#inbox/${latestMessage.id}`
    : `https://mail.google.com/mail/u/0/#inbox`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl">
        {/* Header */}
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="text-base font-semibold leading-snug text-foreground">
              {subject}
            </div>
            {thread && (
              <div className="mt-0.5 text-xs text-muted-foreground">
                {thread.messages.length} message
                {thread.messages.length === 1 ? "" : "s"} in thread
              </div>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-8 gap-1.5 px-2 text-xs"
              onClick={toggleRead}
              disabled={marking || !thread}
              title={isUnread ? "Mark as read" : "Mark as unread"}
            >
              {marking ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : isUnread ? (
                <MailOpen className="h-3.5 w-3.5" />
              ) : (
                <Mail className="h-3.5 w-3.5" />
              )}
              {isUnread ? "Mark read" : "Mark unread"}
            </Button>
            <a
              href={gmailUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
              aria-label="Open in Gmail"
              title="Open in Gmail"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={onClose}
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </header>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {error && (
            <div className="m-4 rounded-md border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-600 dark:text-rose-400">
              {error}
            </div>
          )}
          {!thread && !error && (
            <div className="flex h-32 items-center justify-center text-xs text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Loading thread…
            </div>
          )}
          {thread &&
            thread.messages.map((m, idx) => (
              <MessageBlock
                key={m.id}
                msg={m}
                isLast={idx === thread.messages.length - 1}
              />
            ))}
        </div>
      </div>
    </div>
  );
}

function MessageBlock({
  msg,
  isLast,
}: {
  msg: EmailMessage;
  isLast: boolean;
}) {
  const { name, email } = parseFrom(msg.from);
  return (
    <article
      className={cn(
        "px-5 py-4",
        !isLast ? "border-b border-border" : undefined,
        msg.is_unread ? "bg-agno/5" : undefined,
      )}
    >
      <header className="mb-2 flex items-baseline justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-medium text-foreground" title={email}>
            {name}
          </div>
          {msg.to && (
            <div className="text-[11px] text-muted-foreground">
              to {msg.to.length > 60 ? msg.to.slice(0, 60) + "…" : msg.to}
            </div>
          )}
        </div>
        <div className="shrink-0 text-[11px] text-muted-foreground">
          {formatDate(msg.date)}
        </div>
      </header>
      {msg.body_text ? (
        <pre className="whitespace-pre-wrap break-words font-sans text-[13px] leading-relaxed text-foreground">
          {msg.body_text}
        </pre>
      ) : (
        <div className="text-xs italic text-muted-foreground">
          (no plain-text body — open in Gmail to view)
        </div>
      )}
    </article>
  );
}
