import Chat from "@/components/Chat";

/** Compact chat + voice for the embeddable widget (loaded inside an iframe by /widget.js). No document management. */
export default function Embed() { return <Chat embedded />; }
