import type { ReactNode } from "react";
import { IconAlert, IconCheck, IconInfo } from "@/components/icons";

type Tone = "error" | "notice" | "success" | "info";

const TONE: Record<Tone, { box: string; icon: ReactNode }> = {
  error: { box: "border-brick/30 bg-brick-tint text-brick", icon: <IconAlert className="mt-0.5 size-[1.125rem]" /> },
  notice: { box: "border-amber/30 bg-amber-tint text-amber", icon: <IconAlert className="mt-0.5 size-[1.125rem]" /> },
  success: { box: "border-moss/30 bg-moss-tint text-moss", icon: <IconCheck className="mt-0.5 size-[1.125rem]" /> },
  info: { box: "border-rule bg-paper text-graphite", icon: <IconInfo className="mt-0.5 size-[1.125rem]" /> },
};

interface Props {
  tone?: Tone;
  /** ARIA role: "alert" for errors, "status" for updates, "note" for supporting notices. */
  role?: "alert" | "status" | "note";
  children: ReactNode;
  className?: string;
}

export default function Alert({ tone = "error", role = tone === "error" ? "alert" : "note", children, className = "" }: Props) {
  const t = TONE[tone];
  return (
    <div role={role} className={`flex gap-3 rounded-lg border px-4 py-3 text-[0.9375rem] leading-relaxed ${t.box} ${className}`}>
      {t.icon}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
