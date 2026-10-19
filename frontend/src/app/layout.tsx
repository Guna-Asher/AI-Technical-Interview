import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Technical Interview",
  description: "Resume-aware, role-based technical interview practice.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">{children}</body>
    </html>
  );
}
