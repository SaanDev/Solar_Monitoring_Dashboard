"use client";

import { clsx } from "clsx";

export interface RangeOption {
  key: string;
  label: string;
  hours: number;
}

interface Props {
  options: readonly RangeOption[];
  value: string;
  onChange: (key: string) => void;
}

export function RangeSelector({ options, value, onChange }: Props) {
  return (
    <div className="flex gap-1">
      {options.map((o) => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={clsx(
            "rounded px-2 py-0.5 text-[11px] transition-colors",
            value === o.key
              ? "bg-accent-blue/20 text-accent-blue"
              : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
