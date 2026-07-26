import { cn } from "@/lib/cn";

const PADDING = {
  none: "",
  sm: "p-3",
  md: "p-4",
  lg: "p-5",
} as const;

export interface CardProps extends React.HTMLAttributes<HTMLElement> {
  as?: "div" | "section" | "article";
  /** Mirrors the paddings actually in use across the app. */
  padding?: keyof typeof PADDING;
}

/**
 * The panel shell — `rounded-lg border border-surface-border bg-surface-card`
 * — which is currently hand-written at 117 sites across 70 files.
 *
 * `className` goes through `cn()` (tailwind-merge), so a caller can override the
 * default padding or add layout classes without fighting class order. That
 * matters here: many existing cards fuse the shell with a flex/height contract
 * on the same element (`flex h-full min-h-[20rem] flex-col … p-4`), which is
 * exactly why this is adopted incrementally rather than by codemod.
 */
export function Card({
  as: Tag = "div",
  padding = "md",
  className,
  children,
  ...rest
}: CardProps) {
  return (
    <Tag
      className={cn(
        "rounded-lg border border-surface-border bg-surface-card",
        PADDING[padding],
        className
      )}
      {...rest}
    >
      {children}
    </Tag>
  );
}

export interface CardHeaderProps {
  title: React.ReactNode;
  /** Right-aligned controls: a range selector, a link, an UpdatingPill. */
  actions?: React.ReactNode;
  /**
   * Heading level. Identical card titles are currently h2/h3/h4 depending on
   * the file, which breaks the document outline; set this per page context.
   */
  level?: 2 | 3 | 4;
  className?: string;
}

export function CardHeader({
  title,
  actions,
  level = 3,
  className,
}: CardHeaderProps) {
  const Heading = `h${level}` as "h2" | "h3" | "h4";
  return (
    <div className={cn("mb-2 flex items-center justify-between gap-2", className)}>
      <Heading className="text-xs uppercase tracking-wider text-slate-500">
        {title}
      </Heading>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}
