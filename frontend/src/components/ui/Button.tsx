import type { ComponentProps } from "react";
import { Spinner } from "@/components/ui/Spinner";

type Variant = "primary" | "secondary" | "quiet";

const VARIANT: Record<Variant, string> = {
  primary: "bg-cobalt px-5 text-white hover:bg-cobalt-deep",
  secondary: "border border-edge bg-paper px-5 text-ink hover:bg-mist",
  quiet: "px-3 text-cobalt hover:bg-cobalt-tint",
};

interface Props extends ComponentProps<"button"> {
  variant?: Variant;
  /** Shows a spinner. The caller also sets `disabled` and the label text. */
  loading?: boolean;
}

export default function Button({ variant = "primary", loading = false, className = "", children, type = "button", ...rest }: Props) {
  return (
    <button
      type={type}
      className={`inline-flex min-h-11 shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-lg text-[0.9375rem] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${VARIANT[variant]} ${className}`}
      {...rest}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}
