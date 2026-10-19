export default function ProgressBar({ answered, total }: { answered: number; total: number }) {
  const percent = total > 0 ? Math.round((answered / total) * 100) : 0;
  return (
    <div
      role="progressbar"
      aria-label="Interview progress"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={answered}
      className="h-2 w-full overflow-hidden rounded-full bg-slate-200"
    >
      <div className="h-full bg-slate-900 transition-all" style={{ width: `${percent}%` }} />
    </div>
  );
}
