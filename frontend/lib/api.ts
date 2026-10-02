export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Reply = {
  status: "ok" | "refused" | "injection" | "emergency" | "no_knowledge" | "degraded" | "invalid";
  spoken: string;
  summary: string;
  key_points: string[];
  next_steps: string[];
  sources: { n: number; source: string; heading: string }[];
  disclaimer: string;
  pii_redacted: string[];
};

export type AppConfig = {
  assistant_name: string; organization: string; domain: string; greeting: string; mode: string;
  disclaimer: string; input_placeholder: string; starter_questions: string[];
};

export type Doc = { name: string; size: number; chunks: number; status: "indexed" | "pending" };

async function ok<T>(r: Response, fallback: string): Promise<T> {
  if (r.ok) return r.json();
  let detail = fallback;
  try { detail = (await r.json()).detail ?? fallback; } catch { /* keep fallback */ }
  throw new Error(detail);
}

export const getConfig = () => fetch(`${API}/config`).then((r) => ok<AppConfig>(r, "Server is offline"));

export const sendChat = (sessionId: string, message: string) =>
  fetch(`${API}/chat`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  }).then((r) => ok<Reply>(r, "Couldn't reach the assistant"));

export const getToken = (sessionId: string) =>
  fetch(`${API}/token?session_id=${encodeURIComponent(sessionId)}`)
    .then((r) => ok<{ token: string; url: string }>(r, "Voice isn't set up on the server"));

export const listDocs = () => fetch(`${API}/documents`).then((r) => ok<{ documents: Doc[] }>(r, "Couldn't load documents")).then((d) => d.documents);

export function uploadDoc(file: File) {
  const body = new FormData();
  body.append("file", file);
  return fetch(`${API}/documents`, { method: "POST", body }).then((r) => ok<Doc>(r, "Upload failed"));
}

export const deleteDoc = (name: string) =>
  fetch(`${API}/documents/${encodeURIComponent(name)}`, { method: "DELETE" }).then((r) => ok<{ deleted: string }>(r, "Couldn't remove that document"));

export function sessionId(): string {
  try {
    let id = localStorage.getItem("tara-session");
    if (!id) { id = `s-${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`; localStorage.setItem("tara-session", id); }
    return id;
  } catch { return `s-${Math.random().toString(36).slice(2, 18)}`; }
}
