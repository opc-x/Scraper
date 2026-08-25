import { PlayCircle } from "lucide-react";
import { Card } from "@/components/ui/card";
import type { DrillVideo } from "@/lib/types";

export function DrillResultCard({ video }: { video: DrillVideo }) {
  return (
    <a href={`https://www.youtube.com/watch?v=${video.id}`} target="_blank" rel="noreferrer">
      <Card className="flex gap-3 overflow-hidden p-3 transition-colors active:bg-card-foreground/5">
        <div className="relative aspect-video w-32 shrink-0 overflow-hidden rounded-[var(--radius-sm)] bg-muted">
          {video.thumbnail && (
            <img src={video.thumbnail} alt="" className="h-full w-full object-cover" loading="lazy" />
          )}
          <PlayCircle className="absolute inset-0 m-auto text-white/90 drop-shadow" size={28} />
        </div>
        <div className="flex min-w-0 flex-col gap-1 py-0.5">
          <h4 className="line-clamp-2 text-sm font-medium leading-snug">{video.title}</h4>
          <p className="truncate text-xs text-muted-foreground">{video.channel}</p>
        </div>
      </Card>
    </a>
  );
}
