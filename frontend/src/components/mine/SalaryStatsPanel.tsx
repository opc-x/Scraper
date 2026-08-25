import { Skeleton } from "@/components/ui/skeleton";
import { useSalaryStats } from "@/hooks/useSalaryStats";
import { formatUsdAsCny } from "@/lib/format";

export function SalaryStatsPanel() {
  const { data, loading } = useSalaryStats();

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-2">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
    );
  }
  if (!data || data.disclosed === 0) return null;

  const maxCount = Math.max(...data.buckets.map((b) => b.count), 1);

  return (
    <div className="border border-border">
      <div className="flex items-center justify-between border-b border-border px-3.5 py-2.5">
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">薪资统计</span>
        <span className="font-mono text-[11px] text-primary">披露 {data.disclose_rate}%</span>
      </div>

      <div className="flex border-b border-border">
        <div className="flex-1 border-r border-border px-3.5 py-3">
          <p className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground-dim">中位数年薪</p>
          <p className="mt-1 font-mono text-[22px] font-bold text-foreground">
            {formatUsdAsCny(data.median)}
          </p>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">${data.median.toLocaleString()}</p>
        </div>
        <div className="flex-1 px-3.5 py-3">
          <p className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground-dim">P75 年薪</p>
          <p className="mt-1 font-mono text-[22px] font-bold text-primary">{formatUsdAsCny(data.p75)}</p>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">${data.p75.toLocaleString()}</p>
        </div>
      </div>

      <div className="flex flex-col gap-2.5 px-3.5 py-3.5">
        {data.buckets.filter((b) => b.count > 0).map((b) => {
          const pct = Math.max(Math.round((b.count / maxCount) * 100), 3);
          const isTop = b.count === maxCount;
          return (
            <div key={b.label} className="flex items-center gap-2.5">
              <span
                className={`w-[60px] shrink-0 font-mono text-[10px] ${isTop ? "text-primary" : "text-muted-foreground"}`}
              >
                {b.label}
              </span>
              <div className="h-1.5 flex-1 overflow-hidden bg-muted">
                <div
                  className="h-full"
                  style={{ width: `${pct}%`, background: isTop ? "var(--primary)" : "var(--muted-foreground-dim)" }}
                />
              </div>
              <span className="w-8 shrink-0 text-right font-mono text-[10px] text-muted-foreground">{b.count}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
