import * as React from "react";
import { AppHeader } from "@/components/shell/AppHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { JobCard } from "@/components/job/JobCard";
import { useMarkRows } from "@/hooks/useMarkRows";
import { useMarks } from "@/contexts/MarksProvider";

export function Fav() {
  const { rows, loading, reload } = useMarkRows("saved");
  const { saved } = useMarks();

  React.useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saved.size]);

  return (
    <>
      <AppHeader title="收藏" subtitle={rows.length ? `共 ${rows.length} 条` : undefined} />
      <div className="flex flex-col gap-3 px-4">
        {loading && (
          <div className="flex flex-col gap-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-32 w-full" />
            ))}
          </div>
        )}
        {!loading && rows.length === 0 && <EmptyState message="还没有收藏的职位，去数据页看看" />}
        {!loading &&
          rows.map((m) => (
            <JobCard
              key={m.id}
              variant="saved"
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
