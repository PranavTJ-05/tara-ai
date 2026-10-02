import type { Reply } from "@/lib/api";

export default function AnswerCard({ r }: { r: Reply }) {
  const soft = r.status === "refused" || r.status === "injection" || r.status === "invalid";
  return (
    <div className={`answer ${r.status}`}>
      <p className={soft ? "plain-text" : "summary"}>{r.summary || r.spoken}</p>
      {r.key_points.length > 0 && <ul className="points">{r.key_points.map((k, i) => <li key={i}>{k}</li>)}</ul>}
      {r.next_steps.length > 0 && (
        <div className="steps"><h4>What to do next</h4><ol>{r.next_steps.map((k, i) => <li key={i}>{k}</li>)}</ol></div>
      )}
      {r.sources.length > 0 && <div className="sources">{r.sources.map((s) => <span key={s.n} title={s.heading}>{s.source}</span>)}</div>}
      {r.pii_redacted.length > 0 && <p className="note">I left out the personal details you shared ({r.pii_redacted.join(", ").toLowerCase()}).</p>}
      {r.status === "ok" && r.disclaimer && r.key_points.length + r.next_steps.length > 0 && <p className="note">{r.disclaimer}</p>}
    </div>
  );
}
