"use client";

import { Segmented } from "@/components/ui/Segmented";

export interface RangeOption {
  key: string;
  label: string;
  /** Window length used by callers via `RANGES.find(...)!.hours` — keep it. */
  hours: number;
}

interface Props {
  options: readonly RangeOption[];
  value: string;
  onChange: (key: string) => void;
}

/**
 * Thin wrapper over the shared `Segmented` control.
 *
 * Deliberately keeps its own `RangeOption` shape and prop names: 8+ call sites
 * depend on both, and several read the semantic `hours` field off the same
 * array they pass in here. Rendering now routes through Segmented so all range
 * pickers share one appearance and gain `aria-pressed`.
 */
export function RangeSelector({ options, value, onChange }: Props) {
  return (
    <Segmented
      ariaLabel="Time range"
      size="xs"
      value={value}
      onChange={onChange}
      options={options.map((o) => ({ value: o.key, label: o.label }))}
    />
  );
}
