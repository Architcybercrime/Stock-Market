import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Stock_Market — Live Paper Trading Dashboard",
  description: "Autonomous paper trading on Indian equity markets",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link
          rel="preconnect"
          href="https://fonts.googleapis.com"
        />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen font-sans text-text">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 py-6 sm:py-10">{children}</div>
      </body>
    </html>
  );
}
