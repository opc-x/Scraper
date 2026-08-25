import { AppHeader } from "@/components/shell/AppHeader";
import { StatTile } from "@/components/common/StatTile";
import { ChannelPicker } from "@/components/channel/ChannelPicker";
import { ValueTagManager } from "@/components/value/ValueTagManager";
import { useScrapedSummary } from "@/hooks/useScrapedSummary";

export function Home() {
  const { data: summary, loading } = useScrapedSummary();

  return (
    <>
      <AppHeader title="首页" subtitle="渠道总览 · 配置入口" />
      <div className="flex flex-col gap-5 px-4">
        <StatTile
          variant="hero"
          label={`最近 ${summary?.within_days ?? 90} 天抓到`}
          value={loading ? "…" : (summary?.total ?? 0).toLocaleString()}
          sublabel="条职位"
        />
        <ValueTagManager />
        <ChannelPicker />
      </div>
    </>
  );
}
