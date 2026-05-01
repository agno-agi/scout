"use client";

import { useEffect, useMemo, useState } from "react";
import { ContextStatus, listContexts } from "@/lib/scout";
import { useMounted } from "@/hooks/useMounted";
import { BriefingCard, CardSpec } from "./BriefingCard";
import { FollowupsCard } from "./FollowupsCard";
import { UnreadEmailsCard } from "./UnreadEmailsCard";
import { WeekCalendar } from "./WeekCalendar";

// Calendar, Gmail, and Follow-ups all talk to Postgres / Google APIs
// directly via dedicated FastAPI endpoints — no LLM in the loop. Only
// the Web card still uses queryContextWithRetry on the agent (it actually
// benefits from LLM summarization since the underlying tool returns raw
// search results).
const CARDS: CardSpec[] = [
  {
    title: "What's new on the web",
    contextId: "web",
    question:
      "Brief summary of major tech and AI news from the last 24 hours. 4-6 bullet points, each with a source link in parentheses.",
  },
];

export function BriefingPanel() {
  const [contexts, setContexts] = useState<ContextStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mounted = useMounted();

  const tz = useMemo(() => {
    if (!mounted) return "";
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    } catch {
      return "UTC";
    }
  }, [mounted]);

  useEffect(() => {
    listContexts()
      .then(setContexts)
      .catch((err) => setError(String(err)));
  }, []);

  if (error) {
    return (
      <div className="m-6 rounded-md border border-rose-500/20 bg-rose-500/10 p-4 text-sm text-rose-600 dark:text-rose-400">
        Could not reach Scout API: {error}
        <div className="mt-2 text-xs opacity-80">
          Check that scout-api is running at <code>http://localhost:8000</code>.
        </div>
      </div>
    );
  }

  const calendarStatus: "loading" | "ready" | "missing" =
    contexts === null
      ? "loading"
      : contexts.some((c) => c.id === "calendar" && c.ok)
        ? "ready"
        : "missing";

  return (
    <div className="flex h-full flex-col bg-background">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
        <div>
          <h1 className="text-sm font-semibold text-foreground">Briefing</h1>
          <p className="text-xs text-muted-foreground" suppressHydrationWarning>
            {mounted
              ? new Date().toLocaleDateString(undefined, {
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                })
              : ""}
            {contexts ? ` · ${contexts.length} contexts connected` : ""}
          </p>
        </div>
        <div
          className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground"
          suppressHydrationWarning
        >
          {tz}
        </div>
      </header>

      {/* Whole briefing fits the viewport. Each card's content scrolls
          inside the card, never the page. Calendar gets ~5/9 of the
          available height, cards row ~4/9. min-h-0 lets flex children
          shrink below their natural size; min-h-[…] sets a floor so a
          short window doesn't squash everything to nothing. */}
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden p-6">
        <div className="min-h-[280px] flex-[5]">
          {calendarStatus === "ready" ? (
            <WeekCalendar />
          ) : (
            <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-border bg-muted/40 text-xs text-muted-foreground">
              {calendarStatus === "loading"
                ? "Loading calendar…"
                : "Calendar not configured."}
            </div>
          )}
        </div>

        {/* flex (not grid) so each card gets h-full reliably and min-w-0
            lets it shrink below its content width. min-h-[260px] keeps it
            usable on short viewports. */}
        <div className="flex min-h-[260px] flex-[4] flex-col gap-4 lg:flex-row">
          {contexts === null ? (
            <>
              <CardSkeleton />
              <CardSkeleton />
              <CardSkeleton />
            </>
          ) : (
            <>
              <div className="min-h-0 min-w-0 flex-1">
                <UnreadEmailsCard />
              </div>
              <div className="min-h-0 min-w-0 flex-1">
                <FollowupsCard />
              </div>
              <div className="min-h-0 min-w-0 flex-1">
                <BriefingCard spec={CARDS[0]} contexts={contexts} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function CardSkeleton() {
  return (
    <div className="min-h-0 min-w-0 flex-1 animate-pulse rounded-lg border border-border bg-card" />
  );
}
