"use client";

import { useCallback, useEffect, useRef } from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/cn";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** Accessible name for the dialog. */
  label: string;
  /** Hide the built-in close button when the content supplies its own. */
  showClose?: boolean;
  className?: string;
  children: React.ReactNode;
}

/**
 * Accessible modal for the app's two hand-rolled lightboxes.
 *
 * Both previously rendered a bare `<div onClick>` overlay with **no**
 * `role="dialog"`, `aria-modal`, focus trap, focus restore, body-scroll lock or
 * Escape handler — in fact the whole frontend contained zero `onKeyDown`
 * handlers, so this is its first keyboard-dismissible surface.
 */
export function Modal({
  open,
  onClose,
  label,
  showClose = true,
  className,
  children,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreTo = useRef<HTMLElement | null>(null);

  // Remember what had focus so it can be handed back on close.
  useEffect(() => {
    if (!open) return;
    restoreTo.current = document.activeElement as HTMLElement | null;
    return () => restoreTo.current?.focus?.();
  }, [open]);

  // Lock background scroll while open.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;

      // Cycle focus within the dialog.
      const focusables = panelRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusables?.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    },
    [onClose]
  );

  // Move focus into the dialog once it opens.
  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
  }, [open]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={label}
      onKeyDown={onKeyDown}
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4"
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className={cn("flex max-h-[92vh] max-w-[92vw] flex-col items-center gap-3 outline-none", className)}
      >
        {children}
      </div>

      {showClose && (
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-full bg-black/60 text-slate-200 transition-colors hover:bg-accent-blue/70"
        >
          <X className="h-5 w-5" />
        </button>
      )}
    </div>
  );
}
