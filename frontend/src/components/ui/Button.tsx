import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";

const VARIANT = {
  /** The app's dominant action style: tinted, not filled. */
  ghost: "text-slate-500 hover:bg-surface-muted hover:text-slate-300",
  subtle: "bg-surface-muted text-slate-300 hover:bg-accent-blue/30",
  tinted: "bg-accent-blue/20 text-accent-blue hover:bg-accent-blue/30",
  /** Reserve for the single most important action on a screen. */
  primary: "bg-accent-blue text-white hover:bg-accent-blue/90",
  danger: "bg-accent-red/20 text-accent-red hover:bg-accent-red/30",
  outline: "border border-surface-border text-slate-300 hover:bg-surface-muted",
  /** Download / export chip — this exact string is duplicated in 9 files. */
  chip: "gap-1 bg-surface-muted text-slate-300 hover:bg-accent-blue/30",
} as const;

const SIZE = {
  xs: "px-2 py-0.5 text-[11px]",
  sm: "px-2 py-1 text-xs",
  md: "px-3 py-1.5 text-xs",
} as const;

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof VARIANT;
  size?: keyof typeof SIZE;
  icon?: LucideIcon;
}

/**
 * Shared button. The app has 108 hand-styled `<button>` elements in five
 * recurring shapes; `variant` names those shapes rather than inventing new ones.
 *
 * Default is `ghost`, not `primary`, on purpose: the entire app contains exactly
 * one filled button today (the Settings save action), and that restraint is
 * worth preserving — a dashboard of filled buttons has no focal point.
 */
export function Button({
  variant = "ghost",
  size = "sm",
  icon: Icon,
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex items-center justify-center rounded font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-40",
        VARIANT[variant],
        SIZE[size],
        className
      )}
      {...rest}
    >
      {Icon && <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
      {children}
    </button>
  );
}
