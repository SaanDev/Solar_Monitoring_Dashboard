"use client";

import { useState } from "react";
import { ImageOff } from "lucide-react";
import type { SolarImage } from "@/lib/types";
import { formatUtcShort } from "@/lib/formatting";
import { Modal } from "@/components/ui/Modal";

export function SolarImageCard({ image }: { image: SolarImage }) {
  const [open, setOpen] = useState(false);
  const [thumbFailed, setThumbFailed] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="group flex flex-col overflow-hidden rounded-lg border border-surface-border bg-surface-card hover:border-accent-blue/50 transition-colors"
      >
        <div className="flex aspect-square items-center justify-center overflow-hidden bg-black">
          {/* The old handler set display:none, leaving a silent black hole with
              no indication anything had failed. Say so instead. */}
          {thumbFailed ? (
            <div className="flex flex-col items-center gap-1 px-2 text-center">
              <ImageOff className="h-4 w-4 text-slate-500" aria-hidden="true" />
              <span className="text-[10px] text-slate-500">Preview unavailable</span>
            </div>
          ) : (
            <img
              src={image.thumbnail_url}
              alt={`${image.instrument} ${image.wavelength}`}
              className="h-full w-full object-cover opacity-90 transition-opacity group-hover:opacity-100"
              onError={() => setThumbFailed(true)}
            />
          )}
        </div>
        <div className="p-2 text-left">
          <p className="text-xs font-semibold text-slate-200">{image.wavelength}</p>
          <p className="text-xs text-slate-600">{formatUtcShort(image.timestamp)}</p>
        </div>
      </button>

      {/* This overlay previously had no close button at all — backdrop click was
          the only way out, and no way at all via keyboard. */}
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        label={`${image.instrument} ${image.wavelength} — full size`}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- external source */}
        <img
          src={image.full_url}
          alt={`${image.instrument} ${image.wavelength} full`}
          className="max-h-[85vh] max-w-[85vw] rounded"
        />
        <p className="text-center text-xs text-slate-400">
          {image.source} · {image.wavelength} — {formatUtcShort(image.timestamp)}
        </p>
      </Modal>
    </>
  );
}
