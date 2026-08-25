import { Skeleton } from "@/components/ui/skeleton";
import { useScrapedSummary } from "@/hooks/useScrapedSummary";

interface ChannelOverviewProps {
  value: string;
  onChange: (channel: string) => void;
}

export function ChannelOverview({ value, onChange }: ChannelOverviewProps) {
  const { data, loading } = useScrapedSummary();

  if (loading) {
    return <Skeleton className="h-9 w-full" />;
  }
  if (!data) return null;

  const channels = data.channels.filter((channel) => channel.count > 0);

  return (
    <div className="-mx-4 flex items-center gap-2.5 overflow-x-auto border border-border bg-card px-3 py-2 [scrollbar-width:none]">
      <span className="shrink-0 font-mono text-[10px] uppercase tracking-wide text-muted-foreground-dim">渠道筛选</span>
      <button
        type="button"
        aria-pressed={!value}
        onClick={() => onChange("")}
        className={value ? "shrink-0 font-mono text-[11px] text-muted-foreground" : "shrink-0 font-mono text-[11px] font-bold text-primary"}
      >
        全部 {data.total}
      </button>
      {channels.map((channel) => (
        <button
          key={channel.channel}
          type="button"
          aria-pressed={value === channel.channel}
          onClick={() => onChange(channel.channel)}
          className={value === channel.channel ? "shrink-0 font-mono text-[11px] font-bold text-primary" : "shrink-0 font-mono text-[11px] text-foreground hover:text-primary"}
        >
          {channel.channel} {channel.count}
        </button>
      ))}
    </div>
  );
}
