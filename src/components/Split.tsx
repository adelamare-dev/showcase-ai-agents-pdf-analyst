"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { clsx } from "clsx";

// Only fires for writes from other tabs; same-tab writes are picked up by the
// re-render that ends the drag.
function subscribeStorage(onChange: () => void) {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

/**
 * Two-pane horizontal layout with a draggable gutter (VS Code-style).
 *
 * - `left` and `right` each fill their half; the user drags the gutter to
 *   change the split.
 * - Width is stored as a fraction of the container width (0..1) so the
 *   layout adapts when the viewport resizes.
 * - Persisted to localStorage under `persistKey`.
 * - Clamped to [`minFraction`, `1 - minFraction`] so neither pane can
 *   collapse below the configured minimum.
 *
 * Parent must be a fixed-height flex container; both panes fill 100% height.
 */
export function Split({
  left,
  right,
  persistKey,
  initialLeftFraction = 0.32,
  minFraction = 0.3,
}: {
  left: React.ReactNode;
  right: React.ReactNode;
  persistKey: string;
  initialLeftFraction?: number;
  minFraction?: number;
}) {
  // The server snapshot is null, so the server render and hydration both use
  // `initialLeftFraction`; the stored value takes over right after hydration.
  const stored = useSyncExternalStore(
    subscribeStorage,
    () => window.localStorage.getItem(persistKey),
    () => null,
  );
  const n = stored ? Number(stored) : NaN;
  const persisted =
    !Number.isNaN(n) && n >= minFraction && n <= 1 - minFraction
      ? n
      : initialLeftFraction;

  // Non-null only while the gutter is being dragged.
  const [dragFraction, setDragFraction] = useState<number | null>(null);
  const dragging = dragFraction !== null;
  const fraction = dragFraction ?? persisted;
  const containerRef = useRef<HTMLDivElement>(null);

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
      setDragFraction(fraction);
    },
    [fraction],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!dragging || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const raw = (e.clientX - rect.left) / rect.width;
      const next = Math.min(1 - minFraction, Math.max(minFraction, raw));
      setDragFraction(next);
    },
    [dragging, minFraction],
  );

  const onPointerUp = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      try {
        (e.currentTarget as HTMLDivElement).releasePointerCapture(e.pointerId);
      } catch {
        /* releasePointerCapture can throw if not captured. ignore */
      }
      if (dragFraction !== null) {
        window.localStorage.setItem(persistKey, String(dragFraction));
      }
      setDragFraction(null);
    },
    [dragFraction, persistKey],
  );

  useEffect(() => {
    if (!dragging) return;
    const prevCursor = document.body.style.cursor;
    const prevSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
    };
  }, [dragging]);

  const leftPct = `${fraction * 100}%`;

  return (
    <div ref={containerRef} className="flex-1 min-h-0 flex">
      <div
        style={{ width: leftPct }}
        className="shrink-0 min-w-[320px] h-full overflow-hidden border-r border-[var(--line)] bg-[var(--surface)]"
      >
        {left}
      </div>

      {/* Draggable gutter. 6px wide, with a centered 1px visual rail */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Redimensionner le panneau de discussion"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        className={clsx(
          "group relative -ml-[3px] w-[6px] shrink-0 cursor-col-resize select-none touch-none",
          "before:absolute before:inset-y-0 before:left-1/2 before:w-px before:-translate-x-1/2",
          "before:bg-[var(--line)] before:transition-colors",
          dragging
            ? "before:bg-[var(--lilac)]"
            : "hover:before:bg-[var(--lilac)]",
        )}
      >
        <span
          aria-hidden
          className={clsx(
            "absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-8 w-[3px] rounded-full transition-opacity",
            dragging
              ? "opacity-100 bg-[var(--lilac)]"
              : "opacity-0 group-hover:opacity-100 bg-[var(--ink)]",
          )}
        />
      </div>

      <div className="flex-1 min-w-0 h-full overflow-hidden">{right}</div>
    </div>
  );
}
