import Link from "next/link";
import BackendStatus from "@/components/BackendStatus";
import { Mark } from "@/components/icons";
import { APP_NAME } from "@/lib/brand";

/** The shared page frame: header with the wordmark, the page content, and a quiet footer. */
export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="no-print border-b border-rule bg-paper">
        <div className="mx-auto flex h-14 w-full max-w-5xl items-center px-4 sm:px-6">
          <Link href="/" className="-ml-1 flex min-h-11 items-center gap-2.5 rounded-md px-1 text-[1.0625rem] font-semibold tracking-tight">
            <Mark />
            {APP_NAME}
          </Link>
        </div>
      </header>
      <main id="main" className="flex-1">
        {children}
      </main>
      <footer className="no-print border-t border-rule">
        <div className="mx-auto w-full max-w-5xl px-4 py-4 sm:px-6">
          <BackendStatus />
        </div>
      </footer>
    </div>
  );
}
