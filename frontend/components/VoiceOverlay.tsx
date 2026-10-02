"use client";
import { useEffect } from "react";
import Orb from "./Orb";
import type { useVoice } from "@/lib/useVoice";

const CAPTION = { listening: "Listening", thinking: "Thinking", speaking: "Speaking" } as const;

export default function VoiceOverlay({ voice, name, onClose }: { voice: ReturnType<typeof useVoice>; name: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const connecting = voice.state === "connecting";
  const failed = voice.state === "error";
  return (
    <div className="voice" role="dialog" aria-modal="true" aria-label={`Voice conversation with ${name}`}>
      <div className="voice-stage">
        <Orb phase={connecting ? "thinking" : voice.phase} level={voice.level} />
        <p className="voice-caption" aria-live="polite">
          {failed ? "Couldn't start voice" : connecting ? "Connecting…" : voice.muted ? "Mic is off" : CAPTION[voice.phase]}
        </p>
        <p className="voice-heard">{failed ? voice.error : voice.heard ? `“${voice.heard}”` : connecting ? "" : `Say something to ${name}`}</p>
      </div>
      <div className="voice-bar">
        <button className="round" onClick={voice.toggleMute} aria-pressed={voice.muted} disabled={voice.state !== "live"}
          title={voice.muted ? "Turn mic on" : "Turn mic off"}>
          {voice.muted
            ? <svg viewBox="0 0 24 24"><path d="M3 3l18 18M9 9v3a3 3 0 005.1 2.1M15 9.3V6a3 3 0 00-5.9-.8M5 11a7 7 0 0011.2 5.6M19 11a7 7 0 01-.6 2.8M12 18v3" /></svg>
            : <svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v3" /></svg>}
        </button>
        <button className="round end" onClick={onClose} title="End conversation" autoFocus>
          <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>
    </div>
  );
}
