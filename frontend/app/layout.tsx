import { Figtree, Newsreader } from "next/font/google";
import "./globals.css";

const ui = Figtree({ subsets: ["latin"], variable: "--font-ui", display: "swap" });
const serif = Newsreader({ subsets: ["latin"], variable: "--font-serif", display: "swap", style: ["normal", "italic"] });

export const metadata = { title: "Assistant", description: "Voice and chat assistant" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (<html lang="en" className={`${ui.variable} ${serif.variable}`}><body>{children}</body></html>);
}
