import { cn } from "@/lib/cn";

export interface FieldProps {
  label: React.ReactNode;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}

/**
 * Labelled form control.
 *
 * The app has 91 inputs/selects/textareas, 72 `<label>` elements, and **zero**
 * `id`/`htmlFor` attributes — most labels are detached siblings, so nothing is
 * programmatically associated. This renders a *wrapping* label (the pattern
 * already used correctly in `components/analyzer/Slider.tsx`), which gives the
 * association for free with no id bookkeeping and no way to go stale.
 */
export function Field({ label, hint, error, className, children }: FieldProps) {
  return (
    <label className={cn("block space-y-1", className)}>
      <span className="block text-[10px] uppercase tracking-wider text-slate-500">
        {label}
      </span>
      {children}
      {hint && !error ? (
        <span className="block text-[10px] leading-relaxed text-slate-500">{hint}</span>
      ) : null}
      {error ? (
        <span className="block text-[10px] leading-relaxed text-accent-red">{error}</span>
      ) : null}
    </label>
  );
}
