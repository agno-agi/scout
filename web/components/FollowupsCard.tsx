"use client";

import { Check, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  Followup,
  createFollowup,
  fetchFollowups,
  updateFollowupStatus,
} from "@/lib/scout";
import { cn } from "@/lib/utils";
import {
  Card,
  CardBadge,
  CardContent,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { Button } from "./ui/button";

type Group = "overdue" | "today" | "upcoming" | "no-date";

const GROUP_LABEL: Record<Group, string> = {
  overdue: "Overdue",
  today: "Due today",
  upcoming: "Upcoming",
  "no-date": "No due date",
};

function classify(f: Followup, now: Date): Group {
  if (!f.due_at) return "no-date";
  const due = new Date(f.due_at);
  const todayEnd = new Date(now);
  todayEnd.setHours(23, 59, 59, 999);
  if (due < now) return "overdue";
  if (due <= todayEnd) return "today";
  return "upcoming";
}

function formatDue(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function FollowupsCard() {
  const [items, setItems] = useState<Followup[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  function load() {
    setError(null);
    fetchFollowups("pending")
      .then(setItems)
      .catch((err) => setError(String(err)));
  }

  useEffect(load, []);

  async function onCreate(title: string, due_at: string | null) {
    try {
      const created = await createFollowup({ title, due_at });
      setItems((prev) => (prev ? [...prev, created] : [created]));
      setAdding(false);
    } catch (err) {
      setError(String(err));
    }
  }

  async function onMarkDone(id: number) {
    // Optimistic remove — re-fetch on error.
    const prev = items;
    setItems((cur) => cur?.filter((f) => f.id !== id) ?? null);
    try {
      await updateFollowupStatus(id, "done");
    } catch (err) {
      setItems(prev);
      setError(String(err));
    }
  }

  const now = new Date();
  const grouped: Record<Group, Followup[]> = {
    overdue: [],
    today: [],
    upcoming: [],
    "no-date": [],
  };
  for (const f of items ?? []) grouped[classify(f, now)].push(f);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle>Open follow-ups</CardTitle>
          {items && items.length > 0 && (
            <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              {items.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <CardBadge>crm</CardBadge>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setAdding((v) => !v)}
            aria-label={adding ? "Cancel add" : "Add follow-up"}
            title={adding ? "Cancel" : "Add follow-up"}
          >
            {adding ? <X className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 space-y-3 overflow-y-auto">
        {adding && (
          <AddForm onSave={onCreate} onCancel={() => setAdding(false)} />
        )}

        {error && (
          <div className="rounded-md border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-600 dark:text-rose-400">
            {error}
          </div>
        )}

        {items === null && !error && (
          <div className="space-y-2 pt-1">
            <div className="h-3 w-[88%] animate-pulse rounded bg-muted/60" />
            <div className="h-3 w-[72%] animate-pulse rounded bg-muted/50" />
          </div>
        )}

        {items !== null && items.length === 0 && !adding && !error && (
          <div className="rounded-md border border-dashed border-border bg-muted/20 px-3 py-4 text-center text-xs text-muted-foreground">
            <div>No open follow-ups.</div>
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="mt-2 text-foreground underline underline-offset-2 hover:no-underline"
            >
              Add your first one
            </button>
          </div>
        )}

        {(["overdue", "today", "upcoming", "no-date"] as Group[]).map(
          (g) =>
            grouped[g].length > 0 && (
              <div key={g}>
                <div
                  className={cn(
                    "mb-1 text-[10px] font-semibold uppercase tracking-wider",
                    g === "overdue"
                      ? "text-rose-500"
                      : g === "today"
                      ? "text-agno"
                      : "text-muted-foreground",
                  )}
                >
                  {GROUP_LABEL[g]}
                </div>
                <ul className="space-y-1">
                  {grouped[g].map((f) => (
                    <FollowupRow
                      key={f.id}
                      f={f}
                      group={g}
                      onDone={() => onMarkDone(f.id)}
                    />
                  ))}
                </ul>
              </div>
            ),
        )}
      </CardContent>
    </Card>
  );
}

function FollowupRow({
  f,
  group,
  onDone,
}: {
  f: Followup;
  group: Group;
  onDone: () => void;
}) {
  return (
    <li className="group flex items-start gap-2 rounded-md px-1.5 py-1 transition-colors hover:bg-accent/40">
      <button
        type="button"
        onClick={onDone}
        aria-label="Mark done"
        title="Mark done"
        className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border border-border bg-background text-transparent transition-colors hover:border-agno hover:text-agno focus:outline-none focus-visible:ring-1 focus-visible:ring-agno"
      >
        <Check className="h-3 w-3" />
      </button>
      <div className="min-w-0 flex-1">
        <div className="text-sm leading-snug text-foreground">{f.title}</div>
        {(f.due_at || f.notes) && (
          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
            {f.due_at && (
              <span
                className={cn(
                  group === "overdue" ? "font-medium text-rose-500" : undefined,
                )}
              >
                {formatDue(f.due_at)}
              </span>
            )}
            {f.notes && <span className="truncate">— {f.notes}</span>}
          </div>
        )}
      </div>
    </li>
  );
}

function AddForm({
  onSave,
  onCancel,
}: {
  onSave: (title: string, due_at: string | null) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState("");
  const [due, setDue] = useState(""); // datetime-local value, e.g. 2026-05-03T17:00

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!title.trim()) return;
        // datetime-local has no timezone — treat as the user's local TZ and
        // convert to a real ISO string so the server stores absolute UTC.
        const due_at = due ? new Date(due).toISOString() : null;
        onSave(title.trim(), due_at);
        setTitle("");
        setDue("");
      }}
      className="space-y-2 rounded-md border border-border bg-background p-2"
    >
      <input
        type="text"
        autoFocus
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="What needs following up?"
        className="block w-full rounded-md border border-border bg-card px-2.5 py-1.5 text-sm outline-none focus:border-foreground/30"
      />
      <div className="flex items-center gap-2">
        <input
          type="datetime-local"
          value={due}
          onChange={(e) => setDue(e.target.value)}
          className="flex-1 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-foreground outline-none focus:border-foreground/30"
        />
        <Button
          type="submit"
          variant="agno"
          size="sm"
          className="h-7 px-3 text-xs"
          disabled={!title.trim()}
        >
          Add
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onCancel}
          className="h-7 px-2 text-xs"
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
