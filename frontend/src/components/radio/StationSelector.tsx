"use client";

import type { RadioStation } from "@/lib/types";

interface Props {
  stations: RadioStation[];
  selected: string;
  onChange: (id: string) => void;
}

export function StationSelector({ stations, selected, onChange }: Props) {
  return (
    <select
      value={selected}
      onChange={(e) => onChange(e.target.value)}
      className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue"
    >
      <option value="">— Select station —</option>
      {stations.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name} ({s.location})
        </option>
      ))}
    </select>
  );
}
