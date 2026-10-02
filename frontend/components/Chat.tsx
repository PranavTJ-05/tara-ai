"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppConfig, deleteDoc, Doc, getConfig, listDocs, Reply, sendChat, sessionId, uploadDoc } from "@/lib/api";
import { useVoice } from "@/lib/useVoice";
import AnswerCard from "./AnswerCard";
import Sidebar from "./Sidebar";
import VoiceOverlay from "./VoiceOverlay";

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
  const [voiceOpen, setVoiceOpen] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);

  const refreshDocs = useCallback(() => listDocs().then(setDocs).catch(() => {}), []);
  useEffect(() => {
    setSid(sessionId());
    getConfig().then(setCfg).catch(() => setOffline(true));
    refreshDocs();
  }, [refreshDocs]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy]);
  useEffect(() => {                                       // auto-grow the composer
    const f = field.current; if (!f) return;
    f.style.height = "auto"; f.style.height = `${Math.min(f.scrollHeight, 160)}px`;
  }, [input]);

  const voice = useVoice(sid, (q, reply) => setMsgs((m) => [...m, { role: "user", text: q }, { role: "bot", reply }]));

  const openVoice = () => { setVoiceOpen(true); void voice.start(); };
  const closeVoice = () => { setVoiceOpen(false); void voice.stop(); };

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
            {busy && <div className="msg bot"><div className="typing"><span /><span /><span /></div></div>}
            <div ref={end} />
          </div>
        </section>

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
          <button type="button" className="talk" onClick={openVoice} disabled={!sid || offline} aria-label="Talk to the assistant" title="Talk">
            <svg viewBox="0 0 24 24"><path d="M5 10v4M9 6v12M13 3v18M17 8v8M21 11v2" /></svg>
            <span>Talk</span>
          </button>
          <button className="send" disabled={busy || !input.trim()} aria-label="Send">
            <svg viewBox="0 0 24 24"><path d="M12 19V5M6 11l6-6 6 6" /></svg>
          </button>
        </form>
        <p className="fine">{cfg?.disclaimer}</p>
      </main>

      {voiceOpen && <VoiceOverlay voice={voice} name={cfg?.assistant_name ?? "the assistant"} onClose={closeVoice} />}
    </div>
  );
}
