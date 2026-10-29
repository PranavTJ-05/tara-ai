"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppConfig, deleteDoc, Doc, getConfig, listDocs, Reply, sendChat, sessionId, uploadDoc } from "@/lib/api";
import { useVoice } from "@/lib/useVoice";
import AnswerCard from "./AnswerCard";
import Sidebar from "./Sidebar";
import Orb from "./Orb";

type Msg = { role: "user"; text: string } | { role: "bot"; reply: Reply };
const failure = (summary: string): Reply => ({ status: "degraded", spoken: "", summary, key_points: [], next_steps: [], sources: [], disclaimer: "", pii_redacted: [] });

export default function Chat({ embedded = false }: { embedded?: boolean }) {
  const [cfg, setCfg] = useState<AppConfig | null>(null);
  const [offline, setOffline] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sid, setSid] = useState("");
  const [docs, setDocs] = useState<Doc[]>([]);
  const [uploading, setUploading] = useState<string[]>([]);
  const [docError, setDocError] = useState("");
  const [menu, setMenu] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);

  const refreshDocs = useCallback(() => listDocs().then(setDocs).catch(() => {}), []);
  const voice = useVoice(sid, (q, reply) => setMsgs((m) => [...m, { role: "user", text: q }, { role: "bot", reply }]));

  useEffect(() => {
    setSid(sessionId());
    getConfig().then(setCfg).catch(() => setOffline(true));
    refreshDocs();
  }, [refreshDocs]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy, voice.heard, voice.phase]);
  useEffect(() => {                                       // auto-grow the composer
    const f = field.current; if (!f) return;
    f.style.height = "auto"; f.style.height = `${Math.min(f.scrollHeight, 160)}px`;
  }, [input]);

  const toggleVoice = () => {
    if (voice.state === "live" || voice.state === "connecting") {
      void voice.stop();
    } else {
      void voice.start();
    }
  };

  async function ask(text: string) {
    text = text.trim();
    if (!text || busy) return;
    setInput(""); setBusy(true);
    setMsgs((m) => [...m, { role: "user", text }]);
    try { const reply = await sendChat(sid, text); setMsgs((m) => [...m, { role: "bot", reply }]); }
    catch (e) { setMsgs((m) => [...m, { role: "bot", reply: failure(e instanceof Error ? e.message : "Couldn't reach the assistant") }]); }
    finally { setBusy(false); }
  }

  async function upload(files: FileList | File[]) {
    setDocError("");
    for (const file of Array.from(files)) {
      setUploading((u) => [...u, file.name]);
      try { await uploadDoc(file); await refreshDocs(); }
      catch (e) { setDocError(`${file.name}: ${e instanceof Error ? e.message : "upload failed"}`); }
      finally { setUploading((u) => u.filter((n) => n !== file.name)); }
    }
  }

  async function remove(name: string) {
    setDocError("");
    try { await deleteDoc(name); await refreshDocs(); } catch (e) { setDocError(e instanceof Error ? e.message : "Couldn't remove it"); }
  }

  const empty = msgs.length === 0;
  return (
    <div className={`app ${embedded ? "embedded" : ""}`}>
      {!embedded && (
        <Sidebar cfg={cfg} docs={docs} busy={uploading} error={docError} open={menu}
          onUpload={upload} onDelete={remove} onClose={() => setMenu(false)} />
      )}

      <main className="main">
        <header className="top">
          {embedded
            ? <><span className="mark" aria-hidden /><span className="top-title">{cfg ? cfg.assistant_name : offline ? "Server offline" : "Connecting…"}</span></>
            : <>
                <button className="plain menu-btn" onClick={() => setMenu(true)} aria-label="Open knowledge">
                  <svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h10" /></svg>
                </button>
                <span className="top-title">{cfg ? cfg.assistant_name : offline ? "Server offline" : "Connecting…"}</span>
              </>}
        </header>

        <section className="scroll" aria-live="polite">
          <div className="col">
            {empty && cfg && (
              <div className="hello">
                <h1>{cfg.greeting}</h1>
                {cfg.starter_questions.length > 0 && (
                  <div className="starters">{cfg.starter_questions.map((q) => <button key={q} onClick={() => ask(q)}>{q}</button>)}</div>
                )}
              </div>
            )}
            {msgs.map((m, i) => m.role === "user"
              ? <div key={i} className="msg user"><p>{m.text}</p></div>
              : <div key={i} className="msg bot"><AnswerCard r={m.reply} /></div>)}

            {/* Real-time STT preview while speaking/thinking */}
            {voice.state === "live" && voice.heard && (
              <>
                <div className="msg user pending">
                  <p>{voice.heard}</p>
                </div>
                {voice.phase === "thinking" && (
                  <div className="msg bot">
                    <div className="typing"><span /><span /><span /></div>
                  </div>
                )}
              </>
            )}

            {busy && <div className="msg bot"><div className="typing"><span /><span /><span /></div></div>}
            <div ref={end} />
          </div>
        </section>

        {/* Inline Voice Dock */}
        {voice.state !== "idle" && (
          <div className="voice-dock" role="region" aria-label="Active voice conversation">
            <div className="voice-dock-left">
              <Orb phase={voice.state === "connecting" ? "thinking" : voice.phase} level={voice.level} compact />
              <div className="voice-dock-info">
                <div className="voice-dock-status">
                  <span className={`status-dot ${voice.state === "live" ? "active" : ""}`} />
                  {voice.state === "connecting"
                    ? "Connecting to voice…"
                    : voice.muted
                    ? "Microphone is muted"
                    : voice.phase === "speaking"
                    ? `${cfg?.assistant_name ?? "Tara"} is speaking…`
                    : voice.phase === "thinking"
                    ? "Thinking…"
                    : "Listening… Speak anytime"}
                </div>
                <div className="voice-dock-heard">
                  {voice.heard
                    ? `“${voice.heard}”`
                    : voice.state === "connecting"
                    ? "Establishing audio connection…"
                    : `Speak to ${cfg?.assistant_name ?? "Tara"} (or type below)`}
                </div>
              </div>
            </div>
            <div className="voice-dock-actions">
              <button
                type="button"
                className={`btn-voice-tool ${voice.muted ? "muted" : ""}`}
                onClick={voice.toggleMute}
                disabled={voice.state !== "live"}
                title={voice.muted ? "Turn mic on" : "Mute mic"}
                aria-label={voice.muted ? "Turn mic on" : "Mute mic"}
              >
                {voice.muted ? (
                  <svg viewBox="0 0 24 24"><path d="M3 3l18 18M9 9v3a3 3 0 005.1 2.1M15 9.3V6a3 3 0 00-5.9-.8M5 11a7 7 0 0011.2 5.6M19 11a7 7 0 01-.6 2.8M12 18v3" /></svg>
                ) : (
                  <svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v3" /></svg>
                )}
              </button>
              <button
                type="button"
                className="btn-voice-tool end"
                onClick={() => void voice.stop()}
                title="End voice session"
                aria-label="End voice session"
              >
                <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>
            </div>
          </div>
        )}

        <form className="composer" onSubmit={(e) => { e.preventDefault(); void ask(input); }}>
          <input ref={picker} type="file" hidden multiple accept=".pdf,.md,.txt"
            onChange={(e) => { if (e.target.files?.length) void upload(e.target.files); e.target.value = ""; }} />
          {!embedded && (
            <button type="button" className="icon" onClick={() => picker.current?.click()} aria-label="Add documents" title="Add documents">
              <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
            </button>
          )}
          <textarea ref={field} rows={1} value={input} maxLength={1000} aria-label="Message"
            placeholder={cfg?.input_placeholder ?? "Type your question…"}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(input); } }} />
          <button
            type="button"
            className={`talk ${voice.state !== "idle" ? "active" : ""}`}
            onClick={toggleVoice}
            disabled={!sid || offline}
            aria-label={voice.state !== "idle" ? "End voice session" : "Talk to the assistant"}
            title={voice.state !== "idle" ? "End voice session" : "Talk to the assistant"}
          >
            {voice.state !== "idle" ? (
              <>
                <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
                <span>End</span>
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24"><path d="M5 10v4M9 6v12M13 3v18M17 8v8M21 11v2" /></svg>
                <span>Talk</span>
              </>
            )}
          </button>
          <button className="send" disabled={busy || !input.trim()} aria-label="Send">
            <svg viewBox="0 0 24 24"><path d="M12 19V5M6 11l6-6 6 6" /></svg>
          </button>
        </form>
        <p className="fine">{cfg?.disclaimer}</p>
      </main>
    </div>
  );
}
