"use client";

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  Card,
  CardBadge,
  CardContent,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { ContextStatus, queryContextWithRetry } from "@/lib/scout";
import { Button } from "./ui/button";
import { Markdown } from "./Markdown";

type State =
  | { kind: "loading" }
  | { kind: "ready"; text: string }
  | { kind: "error"; message: string }
  | { kind: "skipped"; reason: string };

export type CardSpec = {
  title: string;
  contextId: string;
  question: string;
  emptyHint?: string;
};

export function BriefingCard({
  spec,
  contexts,
}: {
  spec: CardSpec;
  contexts: ContextStatus[];
}) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);

  const ctx = contexts.find((c) => c.id === spec.contextId);
  const skip: { reason: string } | null = !ctx
    ? { reason: `${spec.contextId} not configured` }
    : !ctx.ok
      ? { reason: ctx.detail }
      : null;

  const load = useCallback(async () => {
    if (skip) {
      setState({ kind: "skipped", reason: skip.reason });
      return;
    }
    setRefreshing(true);
    setState({ kind: "loading" });
    try {
      const ans = await queryContextWithRetry(spec.contextId, spec.question);
      const text = ans.text?.trim();
      setState({
        kind: "ready",
        text: text || spec.emptyHint || "_(no results)_",
      });
    } catch (err) {
      setState({ kind: "error", message: String((err as Error).message || err) });
    } finally {
      setRefreshing(false);
    }
  }, [spec.contextId, spec.question, spec.emptyHint, skip]);

  useEffect(() => {
    let cancelled = false;
    void load().catch(() => {});
    return () => {
      cancelled = true;
      void cancelled;
    };
  }, [load]);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <CardTitle>{spec.title}</CardTitle>
        <div className="flex items-center gap-1">
          <CardBadge>{spec.contextId}</CardBadge>
          {!skip && (
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
          )}
        </div>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-y-auto">
        {state.kind === "loading" && <CardSkeleton />}
        {state.kind === "ready" && <Markdown>{state.text}</Markdown>}
        {state.kind === "skipped" && (
          <div className="rounded-md border border-dashed border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            {state.reason}
          </div>
        )}
        {state.kind === "error" && (
          <div className="rounded-md border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-600 dark:text-rose-400">
            {state.message}
            <button
              type="button"
              onClick={() => void load()}
              className="ml-2 underline underline-offset-2 hover:no-underline"
            >
              Retry
            </button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CardSkeleton() {
  return (
    <div className="space-y-2 pt-1">
      <div className="h-3 w-[88%] animate-pulse rounded bg-muted/60" />
      <div className="h-3 w-[72%] animate-pulse rounded bg-muted/50" />
      <div className="h-3 w-[60%] animate-pulse rounded bg-muted/40" />
    </div>
  );
}
