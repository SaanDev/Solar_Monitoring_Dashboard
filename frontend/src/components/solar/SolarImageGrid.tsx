import type { SolarImage } from "@/lib/types";
import { SolarImageCard } from "./SolarImageCard";

interface Props {
  images: SolarImage[];
  loading?: boolean;
}

export function SolarImageGrid({ images, loading }: Props) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="aspect-square animate-pulse rounded-lg bg-surface-muted" />
        ))}
      </div>
    );
  }

  if (!images.length) {
    return (
      <div className="flex h-32 items-center justify-center text-xs text-slate-700">
        No images available
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {images.map((img) => (
        <SolarImageCard key={img.id} image={img} />
      ))}
    </div>
  );
}
