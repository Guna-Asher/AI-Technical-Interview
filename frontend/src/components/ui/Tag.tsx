import type { ReactNode } from "react";

type Tone = "neutral" | "accent" | "success" | "warn" | "danger";

const TONE: Record<Tone, string> = {
  neutral: "border-rule bg-paper text-graphite",
  accent: "border-cobalt/25 bg-cobalt-tint text-cobalt",
  success: "border-moss/25 bg-moss-tint text-moss",
  warn: "border-amber/25 bg-amber-tint text-amber",
  danger: "border-brick/25 bg-brick-tint text-brick",
};

export default function Tag({ tone = "neutral", icon, children }: { tone?: Tone; icon?: ReactNode; children: ReactNode }) {
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[0.8125rem] font-medium ${TONE[tone]}`}>
      {icon}
      {children}
    </span>
  );
}
