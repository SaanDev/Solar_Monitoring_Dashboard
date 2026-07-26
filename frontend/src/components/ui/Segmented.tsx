"use client";

import { cn } from "@/lib/cn";

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  disabled?: boolean;
  /** Native tooltip, e.g. to explain why an option is disabled. */
  title?: string;
}

export interface SegmentedProps<T extends string> {
  options: readonly SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** `xs` matches the chart RangeSelector; `sm` matches the page-level pills. */
  size?: "xs" | "sm";
  /** Names the group for screen readers, e.g. "Time range". */
  ariaLabel?: string;
  className?: string;
}

const SIZE = {
  xs: "px-2 py-0.5 text-[11px]",
  sm: "px-3 py-1 text-xs",
} as const;

/**
 * The segmented pill control, which had been re-implemented ~20 times at five
 * different sizes (two private `Segmented`/`Pills` components plus a dozen
 * inline `flex gap-1` button rows).
 *
 * Selection was previously conveyed by colour alone with no ARIA state, so a
 * screen reader announced every option identically. `role="group"` +
 * `aria-pressed` fixes that for all consumers at once.
 */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  size = "xs",
  ariaLabel,
  className,
}: SegmentedProps<T>) {
  return (
    <div role="group" aria-label={ariaLabel} className={cn("flex gap-1", className)}>
      {options.map((o) => {
        const active = value === o.value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            disabled={o.disabled}
            title={o.title}
            onClick={() => onChange(o.value)}
            className={cn(
              "rounded transition-colors",
              SIZE[size],
              active
                ? "bg-accent-blue/20 text-accent-blue"
                : "text-slate-500 hover:bg-surface-muted hover:text-slate-300",
              o.disabled && "cursor-not-allowed opacity-40 hover:bg-transparent"
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
