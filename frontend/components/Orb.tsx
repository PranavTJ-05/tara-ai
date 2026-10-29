"use client";
import { MutableRefObject, useEffect, useRef } from "react";
import type { Phase } from "@/lib/useVoice";

/** Morphing orb. `level` (0..1) is read every frame and written to a CSS variable, so there are no re-renders. */
export default function Orb({ phase, level, compact = false }: { phase: Phase; level: MutableRefObject<number>; compact?: boolean }) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let raf = 0, smooth = 0;
    const tick = () => {
      smooth += (level.current - smooth) * 0.22;
      el.current?.style.setProperty("--level", smooth.toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [level]);

  return (
    <div ref={el} className={`orb ${phase} ${compact ? "compact" : ""}`} aria-hidden>
      <i className="halo" />
      <div className="body">
        <i className="blob b1" /><i className="blob b2" /><i className="blob b3" /><i className="sheen" />
      </div>
    </div>
  );
}
