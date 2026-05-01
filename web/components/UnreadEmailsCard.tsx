"use client";

import { Mail, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { UnreadEmail, fetchUnreadEmails } from "@/lib/scout";
import {
  Card,
  CardBadge,
  CardContent,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { Button } from "./ui/button";
import { EmailModal } from "./EmailModal";

// "Doe, John <john@example.com>" → { name: "Doe, John", email: "john@example.com" }
function parseFrom(raw: string | null): { name: string; email: string } {
  if (!raw) return { name: "(unknown)", email: "" };
  const m = raw.match(/^\s*"?([^"<]+?)"?\s*<([^>]+)>\s*$/);
  if (m) return { name: m[1].trim(), email: m[2].trim() };
  // No display name — just an address.
  if (raw.includes("@")) return { name: raw.split("@")[0], email: raw };
  return { name: raw, email: "" };
}

function shortDate(raw: string | null): string {
  if (!raw) return "";
  const d = new Date(raw);
  if (isNaN(d.getTime())) return "";
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  if (sameDay) {
    return d.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
  }
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export function UnreadEmailsCard() {
  const [emails, setEmails] = useState<UnreadEmail[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [openThread, setOpenThread] = useState<{
    threadId: string;
    messageId: string;
  } | null>(null);

  const load = useCallback(async () => {
    setError(null);
    setRefreshing(true);
    try {
      const data = await fetchUnreadEmails(50);
      setEmails(data);
    } catch (err) {
      setError(String((err as Error).message || err));
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle>Unread emails</CardTitle>
          {emails && emails.length > 0 && (
            <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              {emails.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <CardBadge>gmail</CardBadge>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => void load()}
            disabled={refreshing}
            aria-label="Refresh"
            title="Refresh"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
            />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-y-auto">
        {error && (
          <div className="mb-2 rounded-md border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-600 dark:text-rose-400">
            {error}
            <button
              type="button"
              onClick={() => void load()}
              className="ml-2 underline underline-offset-2 hover:no-underline"
            >
              Retry
            </button>
          </div>
        )}

        {emails === null && !error && (
          <div className="space-y-2 pt-1">
            <div className="h-3 w-[88%] animate-pulse rounded bg-muted/60" />
            <div className="h-3 w-[72%] animate-pulse rounded bg-muted/50" />
            <div className="h-3 w-[60%] animate-pulse rounded bg-muted/40" />
          </div>
        )}

        {emails && emails.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border bg-muted/20 px-3 py-6 text-xs text-muted-foreground">
            <Mail className="h-4 w-4" />
            Inbox is clear.
          </div>
        )}

        {emails && emails.length > 0 && (
          <ul className="-mx-2 divide-y divide-border/50">
            {emails.map((e) => {
              const { name, email } = parseFrom(e.from);
              return (
                <li key={e.id}>
                  <button
                    type="button"
                    onClick={() =>
                      setOpenThread({
                        threadId: e.thread_id || e.id,
                        messageId: e.id,
                      })
                    }
                    className="group block w-full rounded-md px-2 py-2 text-left transition-colors hover:bg-accent/40"
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span
                        className="truncate text-xs font-medium text-foreground"
                        title={email || name}
                      >
                        {name}
                      </span>
                      <span className="shrink-0 text-[10px] text-muted-foreground">
                        {shortDate(e.date)}
                      </span>
                    </div>
                    <div className="truncate text-sm text-foreground">
                      {e.subject || "(no subject)"}
                    </div>
                    {e.snippet && (
                      <div className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground">
                        {e.snippet}
                      </div>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>

      {openThread && (
        <EmailModal
          threadId={openThread.threadId}
          initialUnread={true}
          onClose={() => setOpenThread(null)}
          onMarked={(messageId, action) => {
            // If the user marked the latest message read from the modal,
            // remove it from the unread list — that's what they expected.
            if (action === "read") {
              setEmails((prev) =>
                prev ? prev.filter((m) => m.id !== messageId) : prev,
              );
            }
          }}
        />
      )}
    </Card>
  );
}
