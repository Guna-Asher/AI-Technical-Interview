/** One segment per question: answered segments are solid, the current one is tinted. */
export default function ProgressBar({ answered, total }: { answered: number; total: number }) {
  return (
    <div
      role="progressbar"
      aria-label="Interview progress"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={answered}
      className="flex w-full gap-1.5"
    >
      {Array.from({ length: total }, (_, index) => (
        <div
          key={index}
          className={`h-1.5 flex-1 rounded-full transition-colors ${
            index < answered ? "bg-cobalt" : index === answered ? "bg-cobalt/35" : "bg-rule"
          }`}
        />
      ))}
    </div>
  );
}
