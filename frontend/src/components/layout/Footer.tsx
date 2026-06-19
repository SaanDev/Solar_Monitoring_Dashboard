const SOURCES = [
  { name: "e-CALLISTO", sub: "ORFEES Radio" },
  { name: "GOES", sub: "NOAA / NASA" },
  { name: "SDO/AIA", sub: "NASA" },
  { name: "SOHO/LASCO", sub: "ESA / NASA" },
  { name: "Kyoto", sub: "WDC-C2" },
  { name: "NOAA SWPC", sub: "Space Weather Prediction Center" },
];

export function Footer() {
  return (
    <footer className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-1 border-t border-surface-border bg-surface-card px-6 py-2 text-xs">
      <span className="font-semibold uppercase tracking-wider text-slate-600">Data Sources</span>
      {SOURCES.map((s) => (
        <span key={s.name} className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-accent-cyan/60" />
          <span className="text-slate-400">{s.name}</span>
          <span className="text-slate-600">· {s.sub}</span>
        </span>
      ))}
      <span className="ml-auto text-slate-600">
        All times in UTC · © 2026 Sahan S Liyanage
      </span>
    </footer>
  );
}
