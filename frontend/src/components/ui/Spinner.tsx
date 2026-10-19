/** A small spinner for buttons. Decorative: the surrounding text says what is happening. */
export function Spinner({ className = "size-4" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${className}`}
    />
  );
}

/** An indeterminate stripe shown while a long request runs. Decorative. */
export function ProgressStripe() {
  return (
    <div aria-hidden="true" className="h-1 w-full overflow-hidden rounded-full bg-cobalt-tint">
      <div className="h-full w-1/3 animate-stripe rounded-full bg-cobalt" />
    </div>
  );
}
