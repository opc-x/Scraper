import * as React from "react";
import { AppHeader } from "@/components/shell/AppHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { JobCard } from "@/components/job/JobCard";
import { SalaryStatsPanel } from "@/components/mine/SalaryStatsPanel";
import { ResumeStudio } from "@/components/mine/ResumeStudio";
import { JobRulesManager } from "@/components/mine/JobRulesManager";
import { useMarkRows } from "@/hooks/useMarkRows";
import { useMarks } from "@/contexts/MarksProvider";

export function Mine() {
  const { rows, loading, reload } = useMarkRows("archived");
  const { archived } = useMarks();

  React.useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [archived.size]);

  return (
    <>
      <AppHeader title="我的" subtitle="上传 · 分析 · 优化 · 归档" />
      <div className="flex flex-col gap-4 px-4">
        <ResumeStudio />
        <JobRulesManager />
        <SalaryStatsPanel />

        <h3 className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">
          归档职位{rows.length ? ` · ${rows.length} 条` : ""}
        </h3>

        {loading && (
          <div className="flex flex-col gap-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-32 w-full" />
            ))}
          </div>
        )}
        {!loading && rows.length === 0 && <EmptyState message="还没有归档的职位" />}
        {!loading &&
          rows.map((m) => (
            <JobCard
              key={m.id}
              variant="archived"
              job={{
                id: m.scraped_job_id ?? 0,
                channel: m.channel,
                external_id: m.external_id,
                title: m.title,
                company: m.company,
                salary: m.salary,
                city: m.city,
                skills: m.skills,
                url: m.url,
                sourceLabel: m.source_label,
                isRemote: m.is_remote,
                valueTags: m.value_tags,
              }}
            />
          ))}
      </div>
    </>
  );
}
