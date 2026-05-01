"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ChatPanel } from "./ChatPanel";
import { BriefingPanel } from "./BriefingPanel";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "scout:splitter";
const DEFAULT_PCT = 30;
const MIN_PX = 320;
const MAX_PCT = 60;

export function Workspace() {
  const [pct, setPct] = useState<number>(DEFAULT_PCT);
  const containerRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const [dragging, setDragging] = useState(false);

  // Load saved width once (client only, post-mount).
  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem(STORAGE_KEY));
      if (Number.isFinite(saved) && saved >= 15 && saved <= MAX_PCT) {
        setPct(saved);
      }
    } catch {
      /* noop */
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(pct));
    } catch {
      /* noop */
    }
  }, [pct]);

  const onMouseDown = useCallback(() => {
    draggingRef.current = true;
    setDragging(true);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    function onMove(e: MouseEvent) {
      if (!draggingRef.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const minPctFromMinPx = (MIN_PX / rect.width) * 100;
      const minPct = Math.max(15, minPctFromMinPx);
      const next = ((e.clientX - rect.left) / rect.width) * 100;
      setPct(Math.max(minPct, Math.min(MAX_PCT, next)));
    }
    function onUp() {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      setDragging(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  // Keyboard nudge on the splitter handle (left/right arrows = ±2%, shift = ±5%).
  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const step = e.shiftKey ? 5 : 2;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      setPct((p) => Math.max(15, p - step));
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      setPct((p) => Math.min(MAX_PCT, p + step));
    } else if (e.key === "Home") {
      e.preventDefault();
      setPct(DEFAULT_PCT);
    }
  }

  return (
    <div
      ref={containerRef}
      className="flex h-screen w-screen overflow-hidden"
    >
      <div style={{ width: `${pct}%` }} className="min-w-0 shrink-0">
        <ChatPanel />
      </div>

      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize chat panel"
        tabIndex={0}
        onMouseDown={onMouseDown}
        onKeyDown={onKeyDown}
        className={cn(
          "group relative w-1 shrink-0 cursor-col-resize bg-border transition-colors hover:bg-agno/60 focus:bg-agno/80 focus:outline-none",
          dragging ? "bg-agno" : undefined,
        )}
      >
        {/* Wider invisible hit area for easier grabbing */}
        <div className="absolute inset-y-0 -left-1.5 -right-1.5" />
        {/* Visible grab handle dots, only on hover/drag */}
        <div
          className={cn(
            "pointer-events-none absolute top-1/2 left-1/2 flex -translate-x-1/2 -translate-y-1/2 flex-col gap-0.5 transition-opacity",
            dragging ? "opacity-100" : "opacity-0 group-hover:opacity-60",
          )}
        >
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-0.5 w-0.5 rounded-full bg-foreground"
            />
          ))}
        </div>
      </div>

      <div className="min-w-0 flex-1">
        <BriefingPanel />
      </div>
    </div>
  );
}
