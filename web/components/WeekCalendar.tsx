"use client";

import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  RefreshCw,
  Video,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CalendarEvent, fetchCalendarEvents } from "@/lib/scout";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";

// Visible time window. Google Calendar default. Events outside this range
// still fetch but render clipped — most people don't have 3am meetings.
const DAY_START_HOUR = 5;
const DAY_END_HOUR = 23;
const HOUR_HEIGHT = 48; // px per hour row
const VISIBLE_HOURS = DAY_END_HOUR - DAY_START_HOUR;

const DAY_LABELS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

function startOfWeek(d: Date): Date {
  const out = new Date(d);
  out.setHours(0, 0, 0, 0);
  out.setDate(out.getDate() - out.getDay()); // back to Sunday
  return out;
}

function addDays(d: Date, n: number): Date {
  const out = new Date(d);
  out.setDate(out.getDate() + n);
  return out;
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function monthLabel(weekStart: Date): string {
  const weekEnd = addDays(weekStart, 6);
  const sameMonth = weekStart.getMonth() === weekEnd.getMonth();
  if (sameMonth) {
    return weekStart.toLocaleDateString(undefined, {
      month: "long",
      year: "numeric",
    });
  }
  return `${weekStart.toLocaleDateString(undefined, { month: "short" })} – ${weekEnd.toLocaleDateString(undefined, { month: "short", year: "numeric" })}`;
}

type ParsedEvent = {
  raw: CalendarEvent;
  start: Date;
  end: Date;
  isAllDay: boolean;
  meetUrl?: string;
};

function parseEvent(e: CalendarEvent): ParsedEvent | null {
  const startStr = e.start?.dateTime || e.start?.date;
  const endStr = e.end?.dateTime || e.end?.date;
  if (!startStr || !endStr) return null;
  const isAllDay = !e.start?.dateTime;
  const start = new Date(startStr);
  const end = new Date(endStr);
  if (isNaN(start.getTime()) || isNaN(end.getTime())) return null;
  const meetUrl =
    e.hangoutLink ||
    e.conferenceData?.entryPoints?.find((p) => p.uri)?.uri ||
    undefined;
  return { raw: e, start, end, isAllDay, meetUrl };
}

export function WeekCalendar() {
  const [weekStart, setWeekStart] = useState<Date>(() => startOfWeek(new Date()));
  const [events, setEvents] = useState<ParsedEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [now, setNow] = useState(new Date());
  const [_reload, setReload] = useState(0); // bumps to re-fire fetch effect
  const fetchTokenRef = useRef(0); // drops out-of-order fetch results

  // Keep "now" indicator fresh.
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(t);
  }, []);

  // Fetch events for the visible week.
  useEffect(() => {
    const myToken = ++fetchTokenRef.current;
    setError(null);
    setEvents(null);
    setRefreshing(true);
    const from = new Date(weekStart).toISOString();
    const to = addDays(weekStart, 7).toISOString();
    fetchCalendarEvents(from, to)
      .then((evs) => {
        if (myToken !== fetchTokenRef.current) return;
        const parsed = evs.map(parseEvent).filter(Boolean) as ParsedEvent[];
        setEvents(parsed);
      })
      .catch((err) => {
        if (myToken !== fetchTokenRef.current) return;
        setError(String(err.message || err));
      })
      .finally(() => {
        if (myToken === fetchTokenRef.current) setRefreshing(false);
      });
    // reloadCountRef is read indirectly via state we don't track — bumping
    // _reload re-runs this effect. ESLint can't see the dep; that's fine.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weekStart, _reload]);


  // Auto-scroll once per week-load. scrollIntoView on a real DOM element
  // (now-indicator on today's week, earliest event otherwise) — pixel
  // scrollTo races with React's commit and silently snaps back to 0.
  // We poll up to ~1s for the target element so the scroll lands even
  // if React hasn't painted yet by the time the effect runs.
  const scrolledForWeekRef = useRef<string | null>(null);
  useEffect(() => {
    if (events === null) return;
    const weekKey = weekStart.toISOString();
    if (scrolledForWeekRef.current === weekKey) return;

    const targetId = isCurrentWeek(weekStart)
      ? "wc-now"
      : earliestEventDomId(events);
    if (!targetId) {
      scrolledForWeekRef.current = weekKey;
      return;
    }

    let cancelled = false;
    let attempts = 0;
    function tryScroll() {
      if (cancelled) return;
      const el = document.getElementById(targetId!);
      if (el) {
        el.scrollIntoView({
          block: "center",
          behavior: "instant" as ScrollBehavior,
        });
        scrolledForWeekRef.current = weekKey;
        return;
      }
      if (attempts++ < 20) {
        setTimeout(tryScroll, 50);
      }
    }
    requestAnimationFrame(tryScroll);
    return () => {
      cancelled = true;
    };
  }, [events, weekStart]);

  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)),
    [weekStart],
  );

  const allDay = useMemo(() => events?.filter((e) => e.isAllDay) ?? [], [events]);
  const timed = useMemo(() => events?.filter((e) => !e.isAllDay) ?? [], [events]);

  const tz = useMemo(() => {
    if (typeof window === "undefined") return "";
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    } catch {
      return "UTC";
    }
  }, []);

  const refresh = useCallback(() => {
    scrolledForWeekRef.current = null; // re-scroll after refresh
    setReload((n) => n + 1);
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col rounded-lg border border-border bg-card">
      {/* Header: month label + nav */}
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Calendar
          </span>
          <span className="text-sm font-semibold text-foreground">
            {monthLabel(weekStart)}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label="Refresh"
            title="Refresh"
            onClick={refresh}
            disabled={refreshing}
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
            />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => {
              // Clear the ref so re-scrolling is forced even when the
              // user is already on today's week — they clicked Today
              // because they want to be back at "now".
              scrolledForWeekRef.current = null;
              setWeekStart(startOfWeek(new Date()));
            }}
          >
            Today
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label="Previous week"
            onClick={() => setWeekStart((w) => addDays(w, -7))}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label="Next week"
            onClick={() => setWeekStart((w) => addDays(w, 7))}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {error && (
        <div className="m-3 rounded-md border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-600 dark:text-rose-400">
          {error}
        </div>
      )}

      {/* Day headers */}
      <div className="grid shrink-0 grid-cols-[56px_repeat(7,1fr)] border-b border-border">
        <div className="border-r border-border px-2 py-2 text-[9px] font-mono uppercase text-muted-foreground">
          {tz.split("/").pop()}
        </div>
        {days.map((d) => {
          const today = isSameDay(d, now);
          const eventCount = (events ?? []).filter(
            (e) => !e.isAllDay && isSameDay(e.start, d),
          ).length;
          return (
            <div
              key={d.toISOString()}
              className={cn(
                "flex flex-col items-center gap-0.5 border-r border-border py-2 last:border-r-0",
                today ? "bg-accent/30" : undefined,
              )}
            >
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                {DAY_LABELS[d.getDay()]}
              </span>
              <span
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full text-sm font-medium",
                  today
                    ? "bg-agno text-agno-foreground"
                    : "text-foreground",
                )}
              >
                {d.getDate()}
              </span>
              <span
                className={cn(
                  "text-[9px] uppercase tracking-wider",
                  eventCount > 0 ? "text-foreground/70" : "text-transparent",
                )}
              >
                {eventCount > 0 ? `${eventCount} evt` : "—"}
              </span>
            </div>
          );
        })}
      </div>

      {/* All-day strip (only render if any) */}
      {allDay.length > 0 && (
        <div className="grid shrink-0 grid-cols-[56px_repeat(7,1fr)] border-b border-border bg-muted/20">
          <div className="border-r border-border px-1 py-1 text-[9px] font-mono uppercase text-muted-foreground">
            all-day
          </div>
          {days.map((d) => (
            <div
              key={d.toISOString()}
              className="min-h-[28px] border-r border-border p-1 last:border-r-0"
            >
              {allDay
                .filter((e) => allDayCovers(e, d))
                .map((e) => (
                  <EventChip key={e.raw.id + d.toISOString()} event={e} compact />
                ))}
            </div>
          ))}
        </div>
      )}

      {/* Scrollable hour grid */}
      <div ref={scrollRef} className="relative min-h-0 flex-1 overflow-y-auto">
        <div
          className="relative grid grid-cols-[56px_repeat(7,1fr)]"
          style={{ minHeight: VISIBLE_HOURS * HOUR_HEIGHT }}
        >
          {/* Hour labels column */}
          <div className="relative border-r border-border">
            {Array.from({ length: VISIBLE_HOURS }).map((_, i) => (
              <div
                key={i}
                className="relative border-b border-border/50 text-[10px] text-muted-foreground"
                style={{ height: HOUR_HEIGHT }}
              >
                <span className="absolute -top-1.5 right-2">
                  {formatHourLabel(DAY_START_HOUR + i)}
                </span>
              </div>
            ))}
          </div>

          {/* 7 day columns */}
          {days.map((d) => (
            <DayColumn
              key={d.toISOString()}
              day={d}
              events={timed.filter((e) => isSameDay(e.start, d))}
              now={now}
              showNow={isSameDay(d, now)}
            />
          ))}
        </div>

        {events === null && !error && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
            Loading events…
          </div>
        )}
      </div>
    </div>
  );
}

function DayColumn({
  day,
  events,
  now,
  showNow,
}: {
  day: Date;
  events: ParsedEvent[];
  now: Date;
  showNow: boolean;
}) {
  return (
    <div className="relative border-r border-border last:border-r-0">
      {/* Hour grid lines */}
      {Array.from({ length: VISIBLE_HOURS }).map((_, i) => (
        <div
          key={i}
          className="border-b border-border/50"
          style={{ height: HOUR_HEIGHT }}
        />
      ))}

      {/* Events positioned absolutely */}
      {events.map((e) => {
        const top = minutesIntoDay(e.start) - DAY_START_HOUR * 60;
        const heightMin = Math.max(
          15,
          (e.end.getTime() - e.start.getTime()) / 60_000,
        );
        if (top < 0 || top > VISIBLE_HOURS * 60) return null;
        return (
          <div
            key={e.raw.id}
            id={`wc-evt-${e.raw.id}`}
            className="absolute inset-x-1"
            style={{
              top: (top / 60) * HOUR_HEIGHT,
              height: (heightMin / 60) * HOUR_HEIGHT - 2,
            }}
          >
            <EventChip event={e} />
          </div>
        );
      })}

      {/* Now indicator */}
      {showNow && (
        <NowLine
          minutesPastDayStart={
            now.getHours() * 60 + now.getMinutes() - DAY_START_HOUR * 60
          }
        />
      )}
    </div>
  );
}

function NowLine({ minutesPastDayStart }: { minutesPastDayStart: number }) {
  if (minutesPastDayStart < 0 || minutesPastDayStart > VISIBLE_HOURS * 60)
    return null;
  const top = (minutesPastDayStart / 60) * HOUR_HEIGHT;
  return (
    <div
      id="wc-now"
      className="pointer-events-none absolute inset-x-0 z-10 flex items-center"
      style={{ top: top - 6 }}
    >
      <div className="h-3 w-3 -translate-x-1.5 rounded-full bg-agno" />
      <div className="h-px flex-1 bg-agno" />
    </div>
  );
}

function earliestEventDomId(events: ParsedEvent[]): string | null {
  const timed = events
    .filter((e) => !e.isAllDay)
    .sort((a, b) => a.start.getTime() - b.start.getTime());
  if (timed.length === 0) return null;
  return `wc-evt-${timed[0].raw.id}`;
}

function EventChip({
  event,
  compact = false,
}: {
  event: ParsedEvent;
  compact?: boolean;
}) {
  const title = event.raw.summary || "(no title)";
  const timeLabel = compact
    ? null
    : `${formatTime(event.start)} – ${formatTime(event.end)}`;
  const link =
    event.meetUrl || event.raw.htmlLink || undefined;

  return (
    <div
      className={cn(
        "group h-full overflow-hidden rounded-md border border-sky-500/30 bg-sky-500/15 px-1.5 py-0.5 text-[11px] text-sky-900 dark:border-sky-400/30 dark:bg-sky-400/10 dark:text-sky-100",
        compact ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-900 dark:border-emerald-400/30 dark:bg-emerald-400/10 dark:text-emerald-100" : undefined,
      )}
      title={`${title}${timeLabel ? "\n" + timeLabel : ""}`}
    >
      <div className="flex min-w-0 items-center justify-between gap-1">
        <span className="truncate font-medium">{title}</span>
        {link && (
          <a
            href={link}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="shrink-0 opacity-0 transition group-hover:opacity-100"
            aria-label="Open in Google Calendar"
          >
            {event.meetUrl ? (
              <Video className="h-3 w-3" />
            ) : (
              <ExternalLink className="h-3 w-3" />
            )}
          </a>
        )}
      </div>
      {timeLabel && <div className="truncate text-[10px] opacity-80">{timeLabel}</div>}
    </div>
  );
}

// Helpers

function minutesIntoDay(d: Date): number {
  return d.getHours() * 60 + d.getMinutes();
}

function formatTime(d: Date): string {
  return d.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatHourLabel(hour: number): string {
  if (hour === 0) return "12 AM";
  if (hour === 12) return "12 PM";
  if (hour < 12) return `${hour} AM`;
  return `${hour - 12} PM`;
}

function isCurrentWeek(weekStart: Date): boolean {
  const thisStart = startOfWeek(new Date());
  return isSameDay(weekStart, thisStart);
}

function allDayCovers(e: ParsedEvent, day: Date): boolean {
  // All-day events have an exclusive end date in Google Calendar
  // (start.date = day, end.date = day+N+1)
  const dayStart = new Date(day);
  dayStart.setHours(0, 0, 0, 0);
  const dayEnd = new Date(dayStart);
  dayEnd.setDate(dayEnd.getDate() + 1);
  return e.start < dayEnd && e.end > dayStart;
}
