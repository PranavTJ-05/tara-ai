"use client";
import { Room, RoomEvent, Track } from "livekit-client";
import { MutableRefObject, useCallback, useEffect, useRef, useState } from "react";
import { getToken, Reply } from "./api";

export type VoiceState = "idle" | "connecting" | "live" | "error";
export type Phase = "listening" | "thinking" | "speaking";

/** RMS loudness (0..1) of a media track, read on demand. */
function meter(ctx: AudioContext, track: MediaStreamTrack) {
  const src = ctx.createMediaStreamSource(new MediaStream([track]));
  const an = ctx.createAnalyser();
  an.fftSize = 512;
  src.connect(an);
  const buf = new Uint8Array(an.fftSize);
  return {
    read() {
      an.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) { const d = (v - 128) / 128; sum += d * d; }
      return Math.min(1, Math.sqrt(sum / buf.length) * 4);
    },
    stop() { try { src.disconnect(); } catch { /* already gone */ } },
  };
}

type Meter = ReturnType<typeof meter>;

/**
 * Joins the LiveKit room (room name = chat session id). Exposes the conversation phase and a live loudness
 * level for the orb. If the server has no voice model available, the reply is read aloud with the browser's
 * own speech engine instead, so the user always hears an answer.
 */
export function useVoice(sessionId: string, onAnswer: (question: string, reply: Reply) => void) {
  const [state, setState] = useState<VoiceState>("idle");
  const [phase, setPhase] = useState<Phase>("listening");
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState("");
  const [heard, setHeard] = useState("");
  const level = useRef(0);
  const room = useRef<Room | null>(null);
  const cb = useRef(onAnswer);
  cb.current = onAnswer;
  const mutedRef = useRef(false);
  const thinking = useRef(false);
  const synth = useRef(false);          // browser speech in progress
  const raf = useRef(0);
  const ctx = useRef<AudioContext | null>(null);
  const mic = useRef<Meter | null>(null);
  const agent = useRef<Meter | null>(null);

  const setMic = useCallback(async (on: boolean) => {
    try { await room.current?.localParticipant.setMicrophoneEnabled(on); } catch { /* room closing */ }
  }, []);

  const speak = useCallback((text: string) => {
    if (!text || typeof speechSynthesis === "undefined") return;
    const voices = speechSynthesis.getVoices();
    const voice = voices.find((v) => /^en/i.test(v.lang) && /(natural|google|samantha|aria|jenny|neural)/i.test(v.name))
      ?? voices.find((v) => /^en/i.test(v.lang));
    const u = new SpeechSynthesisUtterance(text);
    if (voice) u.voice = voice;
    u.rate = 1.03;
    const done = () => { synth.current = false; if (!mutedRef.current) void setMic(true); };
    u.onend = done; u.onerror = done;
    synth.current = true;
    thinking.current = false;
    void setMic(false);                 // don't let the mic hear the speaker
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  }, [setMic]);

  const stop = useCallback(async () => {
    cancelAnimationFrame(raf.current);
    if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
    synth.current = false;
    mic.current?.stop(); agent.current?.stop(); mic.current = agent.current = null;
    void ctx.current?.close(); ctx.current = null;
    await room.current?.disconnect();
    room.current = null;
    level.current = 0;
    setState("idle"); setMuted(false); mutedRef.current = false; setHeard("");
  }, []);

  const start = useCallback(async () => {
    setError(""); setState("connecting"); setPhase("listening"); setHeard("");
    try {
      const { token, url } = await getToken(sessionId);
      const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      ctx.current = new AC();
      void ctx.current.resume();
      const r = new Room({ adaptiveStream: true, dynacast: true });

      r.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind !== Track.Kind.Audio) return;
        document.body.appendChild(track.attach());
        if (ctx.current) agent.current = meter(ctx.current, track.mediaStreamTrack);
      });
      r.on(RoomEvent.TrackUnsubscribed, (track) => track.detach().forEach((el) => el.remove()));
      r.on(RoomEvent.LocalTrackPublished, (pub) => {
        if (pub.kind === Track.Kind.Audio && pub.track && ctx.current) {
          mic.current?.stop();
          mic.current = meter(ctx.current, pub.track.mediaStreamTrack);
        }
      });
      r.on(RoomEvent.DataReceived, (payload, _p, _k, topic) => {
        let msg: Record<string, unknown>;
        try { msg = JSON.parse(new TextDecoder().decode(payload)); } catch { return; }
        if (topic === "state") {
          if (msg.type === "thinking") thinking.current = true;
          if (msg.type === "ready" && msg.tts === false) speak(String(msg.greeting ?? ""));
        } else if (topic === "answer") {
          const { question, tts, ...reply } = msg as { question: string; tts?: boolean } & Reply;
          setHeard(question);
          cb.current(question, reply as Reply);
          if (tts === false) speak(reply.spoken); else setTimeout(() => { thinking.current = false; }, 12000);
        }
      });
      r.on(RoomEvent.Disconnected, () => { room.current = null; setState("idle"); });

      await r.connect(url, token);
      room.current = r;
      await r.localParticipant.setMicrophoneEnabled(true);    // must follow a user gesture (Safari)
      try { await r.startAudio(); } catch { /* autoplay policy: user already clicked */ }
      setState("live");

      // One loop: measure loudness, derive the phase, feed the orb.
      let last: Phase = "listening", holdUntil = 0;
      const tick = (t: number) => {
        const agentLevel = synth.current ? 0.35 + 0.25 * Math.sin(t / 110) : agent.current?.read() ?? 0;
        const micLevel = mic.current?.read() ?? 0;
        if (agentLevel > 0.05) holdUntil = t + 350;
        const speaking = t < holdUntil;
        if (speaking) thinking.current = false;
        const next: Phase = speaking ? "speaking" : thinking.current ? "thinking" : "listening";
        if (next !== last) { last = next; setPhase(next); }
        level.current = next === "speaking" ? agentLevel : next === "thinking" ? 0.12 + 0.08 * Math.sin(t / 260) : micLevel;
        raf.current = requestAnimationFrame(tick);
      };
      raf.current = requestAnimationFrame(tick);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start voice");
      setState("error");
      await stop();
      setState("error");
    }
  }, [sessionId, speak, stop]);

  const toggleMute = useCallback(async () => {
    mutedRef.current = !mutedRef.current;
    setMuted(mutedRef.current);
    await setMic(!mutedRef.current);
  }, [setMic]);

  useEffect(() => () => { void stop(); }, [stop]);
  return { state, phase, level: level as MutableRefObject<number>, muted, error, heard, start, stop, toggleMute };
}
