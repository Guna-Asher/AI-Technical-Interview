import type { Metadata, Viewport } from "next";
import AppShell from "@/components/AppShell";
import { APP_DESCRIPTION, APP_NAME } from "@/lib/brand";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: APP_NAME, template: `%s · ${APP_NAME}` },
  description: APP_DESCRIPTION,
  applicationName: APP_NAME,
  openGraph: { title: APP_NAME, description: APP_DESCRIPTION, type: "website" },
};

export const viewport: Viewport = { themeColor: "#f6f7f9" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a
          href="#main"
          className="sr-only rounded-md bg-paper px-4 font-medium focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:inline-flex focus:min-h-11 focus:items-center"
        >
          Skip to content
        </a>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
