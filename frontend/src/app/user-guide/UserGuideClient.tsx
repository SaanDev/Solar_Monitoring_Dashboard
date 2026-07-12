"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Search,
  X,
  ChevronDown,
  Compass,
  Activity,
  Radio,
  Microscope,
  CalendarRange,
  Settings,
  BookOpenText,
  ArrowRight,
  ExternalLink,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";

import type { ReferenceBlock } from "@/lib/referenceContent";
import {
  GUIDE_CATEGORIES,
  GUIDE_ENTRIES,
  entrySearchText,
  type GuideCategory,
  type GuideEntry,
} from "@/lib/userGuideContent";

const CATEGORY_STYLE: Record<
  GuideCategory,
  { icon: LucideIcon; text: string; dot: string; ring: string }
> = {
  "getting-started": {
    icon: BookOpenText,
    text: "text-accent-cyan",
    dot: "bg-accent-cyan",
    ring: "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan",
  },
  monitoring: {
    icon: Activity,
    text: "text-accent-blue",
    dot: "bg-accent-blue",
    ring: "border-accent-blue/40 bg-accent-blue/10 text-accent-blue",
  },
  radio: {
    icon: Radio,
    text: "text-accent-orange",
    dot: "bg-accent-orange",
    ring: "border-accent-orange/40 bg-accent-orange/10 text-accent-orange",
  },
  analysis: {
    icon: Microscope,
    text: "text-accent-purple",
    dot: "bg-accent-purple",
    ring: "border-accent-purple/40 bg-accent-purple/10 text-accent-purple",
  },
  events: {
    icon: CalendarRange,
    text: "text-accent-green",
    dot: "bg-accent-green",
    ring: "border-accent-green/40 bg-accent-green/10 text-accent-green",
  },
  settings: {
    icon: Settings,
    text: "text-accent-yellow",
    dot: "bg-accent-yellow",
    ring: "border-accent-yellow/40 bg-accent-yellow/10 text-accent-yellow",
  },
  concepts: {
    icon: Compass,
    text: "text-accent-red",
    dot: "bg-accent-red",
    ring: "border-accent-red/40 bg-accent-red/10 text-accent-red",
  },
};

// Precompute the search haystack once per entry (module data is static).
const SEARCH_INDEX = new Map(
  GUIDE_ENTRIES.map((e) => [e.id, entrySearchText(e)] as const)
);

export function UserGuideClient() {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());

  const q = query.trim().toLowerCase();
  const searching = q.length > 0;

  const matched = useMemo(() => {
    if (!searching) return GUIDE_ENTRIES;
    return GUIDE_ENTRIES.filter((e) => SEARCH_INDEX.get(e.id)!.includes(q));
  }, [q, searching]);

  const byCategory = useMemo(() => {
    const map = Object.fromEntries(
      GUIDE_CATEGORIES.map((c) => [c.id, [] as GuideEntry[]])
    ) as Record<GuideCategory, GuideEntry[]>;
    for (const e of matched) map[e.category].push(e);
    return map;
  }, [matched]);

  const toggle = (id: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const jumpTo = (id: string) => {
    document.getElementById(`section-${id}`)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  const isOpen = (id: string) => searching || open.has(id);

  return (
    <div className="mx-auto max-w-5xl">
      {/* Sticky toolbar: search + category jump-nav (full-bleed within the padded main).
          The before:* pseudo-element masks main's top padding so entries don't bleed
          into the gap above the bar when it is stuck. */}
      <div className="sticky top-0 z-20 -mx-6 mb-6 border-b border-surface-border bg-surface px-6 pb-4 pt-6 before:pointer-events-none before:absolute before:inset-x-0 before:bottom-full before:h-6 before:bg-surface">
        <div className="mx-auto max-w-5xl">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search pages, controls, concepts…"
              className="w-full rounded-md border border-surface-border bg-surface-card py-2 pl-9 pr-9 text-sm text-slate-200 placeholder:text-slate-500 focus:border-accent-blue focus:outline-none focus:ring-1 focus:ring-accent-blue"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-500 hover:text-slate-300"
                aria-label="Clear search"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {GUIDE_CATEGORIES.map((cat) => {
              const style = CATEGORY_STYLE[cat.id];
              const count = byCategory[cat.id].length;
              const Icon = style.icon;
              return (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => jumpTo(cat.id)}
                  disabled={count === 0}
                  className={clsx(
                    "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                    count === 0
                      ? "cursor-default border-surface-border text-slate-600"
                      : "border-surface-border text-slate-300 hover:bg-surface-muted"
                  )}
                >
                  <Icon className={clsx("h-3.5 w-3.5", count > 0 && style.text)} />
                  {cat.label}
                  <span className="text-slate-500">{count}</span>
                </button>
              );
            })}
            {searching && (
              <span className="ml-auto text-xs text-slate-500">
                {matched.length} result{matched.length === 1 ? "" : "s"}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Intro */}
      {!searching && (
        <p className="mb-8 max-w-3xl text-sm leading-relaxed text-slate-400">
          A complete walkthrough of the dashboard: how to{" "}
          <span className="text-accent-blue">read every monitoring page</span>,
          operate the <span className="text-accent-orange">radio</span> and{" "}
          <span className="text-accent-purple">analysis</span> tools, use the{" "}
          <span className="text-accent-green">forecast, timeline and archive</span>,
          and the <span className="text-accent-red">concepts</span> you need to
          interpret the data. Use the search box to jump straight to a page or term.
        </p>
      )}

      {matched.length === 0 ? (
        <div className="rounded-lg border border-surface-border bg-surface-card p-8 text-center">
          <p className="text-sm text-slate-400">No entries match “{query}”.</p>
          <button
            type="button"
            onClick={() => setQuery("")}
            className="mt-3 text-xs text-accent-blue hover:underline"
          >
            Clear search
          </button>
        </div>
      ) : (
        <div className="space-y-10">
          {GUIDE_CATEGORIES.map((cat) => {
            const entries = byCategory[cat.id];
            if (entries.length === 0) return null;
            const style = CATEGORY_STYLE[cat.id];
            const Icon = style.icon;
            return (
              <section key={cat.id} id={`section-${cat.id}`} className="scroll-mt-28">
                <div className="mb-3 flex items-center gap-2">
                  <Icon className={clsx("h-5 w-5", style.text)} />
                  <h2 className="text-lg font-semibold text-slate-100">{cat.label}</h2>
                  <span className="text-xs text-slate-500">({entries.length})</span>
                </div>
                {!searching && (
                  <p className="mb-4 max-w-3xl text-sm text-slate-500">{cat.blurb}</p>
                )}
                <div className="space-y-3">
                  {entries.map((entry) => (
                    <EntryCard
                      key={entry.id}
                      entry={entry}
                      open={isOpen(entry.id)}
                      onToggle={() => toggle(entry.id)}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function EntryCard({
  entry,
  open,
  onToggle,
}: {
  entry: GuideEntry;
  open: boolean;
  onToggle: () => void;
}) {
  const style = CATEGORY_STYLE[entry.category];
  return (
    <div
      id={`section-${entry.id}`}
      className="scroll-mt-28 overflow-hidden rounded-lg border border-surface-border bg-surface-card"
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-muted/50"
      >
        <span className={clsx("mt-1.5 h-2 w-2 shrink-0 rounded-full", style.dot)} />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-sm font-semibold text-slate-100">{entry.title}</span>
            {entry.tags?.map((tag) => (
              <span
                key={tag}
                className="rounded-full bg-surface-muted px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-500"
              >
                {tag}
              </span>
            ))}
          </span>
          <span className="mt-1 block text-xs leading-relaxed text-slate-400">
            {entry.short}
          </span>
        </span>
        <ChevronDown
          className={clsx(
            "mt-1 h-4 w-4 shrink-0 text-slate-500 transition-transform",
            open && "rotate-180"
          )}
        />
      </button>

      {open && (
        <div className="border-t border-surface-border px-4 py-4 pl-9">
          <div className="space-y-3">
            {entry.body.map((block, i) => (
              <BlockView key={i} block={block} />
            ))}
          </div>

          {(entry.link || entry.references?.length) && (
            <div className="mt-4 space-y-3 border-t border-surface-border pt-3">
              {entry.link && (
                <Link
                  href={entry.link.href}
                  className={clsx(
                    "inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:brightness-110",
                    style.ring
                  )}
                >
                  {entry.link.label}
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              )}
              {entry.references?.length ? (
                <div className="flex flex-col gap-1 sm:flex-row sm:gap-3">
                  <span className="w-24 shrink-0 text-[10px] uppercase tracking-widest text-slate-600">
                    References
                  </span>
                  <span className="flex min-w-0 flex-1 flex-wrap gap-x-4 gap-y-1">
                    {entry.references.map((ref) => (
                      <a
                        key={ref.url}
                        href={ref.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-accent-blue hover:underline"
                      >
                        {ref.label}
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    ))}
                  </span>
                </div>
              ) : null}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function BlockView({ block }: { block: ReferenceBlock }) {
  switch (block.kind) {
    case "para":
      return <p className="text-sm leading-relaxed text-slate-300">{block.text}</p>;
    case "list":
      return (
        <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-300 marker:text-slate-600">
          {block.items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      );
    case "formula":
      return (
        <div className="rounded-md border border-surface-border bg-surface-muted px-4 py-3">
          <code className="font-mono text-sm text-accent-cyan">{block.expr}</code>
          {block.note && (
            <p className="mt-2 text-xs leading-relaxed text-slate-500">{block.note}</p>
          )}
        </div>
      );
    case "table":
      return (
        <div className="overflow-x-auto">
          {block.caption && (
            <p className="mb-1.5 text-xs text-slate-500">{block.caption}</p>
          )}
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="border-b border-surface-border text-left">
                {block.columns.map((col) => (
                  <th
                    key={col}
                    className="px-2 py-1.5 font-medium uppercase tracking-wide text-slate-500"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r} className="border-b border-surface-border/50 last:border-0">
                  {row.map((cell, c) => (
                    <td
                      key={c}
                      className={clsx(
                        "px-2 py-1.5 align-top",
                        c === 0 ? "font-medium text-slate-200" : "text-slate-400"
                      )}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
  }
}
