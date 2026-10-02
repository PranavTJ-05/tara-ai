"use client";
import { useRef, useState } from "react";
import type { AppConfig, Doc } from "@/lib/api";

const kb = (n: number) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1048576).toFixed(1)} MB`);

type Props = {
  cfg: AppConfig | null; docs: Doc[]; busy: string[]; error: string; open: boolean;
  onUpload: (files: FileList | File[]) => void; onDelete: (name: string) => void; onClose: () => void;
};

export default function Sidebar({ cfg, docs, busy, error, open, onUpload, onDelete, onClose }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  return (
    <>
      <div className={`scrim ${open ? "show" : ""}`} onClick={onClose} />
      <aside className={`side ${open ? "open" : ""}`}>
        <div className="brand">
          <span className="mark" aria-hidden />
          <div><strong>{cfg?.assistant_name ?? "Assistant"}</strong><small>{cfg?.organization || cfg?.domain || ""}</small></div>
        </div>

        <div className="side-head">
          <h2>Knowledge</h2>
          <button className="plain" onClick={() => input.current?.click()}>Add files</button>
        </div>
        <input ref={input} type="file" hidden multiple accept=".pdf,.md,.txt"
          onChange={(e) => { if (e.target.files?.length) onUpload(e.target.files); e.target.value = ""; }} />

        <div className={`drop ${drag ? "over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files.length) onUpload(e.dataTransfer.files); }}>
          <p>Drop PDF, Markdown or text files here</p>
        </div>
        {error && <p className="side-error" role="alert">{error}</p>}

        <ul className="docs">
          {busy.map((n) => (
            <li key={`b-${n}`} className="doc working"><span className="spin" aria-hidden /><div><b>{n}</b><small>Reading and indexing…</small></div></li>
          ))}
          {docs.map((d) => (
            <li key={d.name} className="doc">
              <svg viewBox="0 0 24 24" aria-hidden><path d="M7 3h7l5 5v13H7zM14 3v5h5" /></svg>
              <div><b title={d.name}>{d.name}</b><small>{d.chunks ? `${d.chunks} sections` : "Not indexed yet"} · {kb(d.size)}</small></div>
              <button className="x" onClick={() => onDelete(d.name)} aria-label={`Remove ${d.name}`} title="Remove">
                <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>
            </li>
          ))}
          {!docs.length && !busy.length && <li className="empty">No documents yet. Add some and the assistant will answer from them.</li>}
        </ul>

        <div className="side-foot">
          <span className="dot" aria-hidden />
          {cfg ? (cfg.mode === "prompt" ? "Answers from guidelines" : cfg.mode === "rag" ? "Answers only from documents" : "Guidelines and documents") : "Offline"}
        </div>
      </aside>
    </>
  );
}
