import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Stock_Market — Institutional Dashboard",
  description: "Institutional AI trading platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-mono">
        <header className="border-b border-border bg-panel">
          <div className="mx-auto max-w-7xl px-6 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-2 w-2 rounded-full bg-good" />
              <h1 className="text-sm font-semibold tracking-wider uppercase">
                Stock_Market
              </h1>
              <span className="text-muted text-xs">paper mode</span>
            </div>
            <nav className="text-sm flex gap-6 text-muted">
              <a href="/" className="hover:text-text">Dashboard</a>
              <a href="/risk" className="hover:text-text">Risk</a>
              <a href="/signals" className="hover:text-text">Signals</a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
