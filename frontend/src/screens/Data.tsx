import * as React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowDownWideNarrow, ArrowUpWideNarrow, Plus } from "lucide-react";
import { AppHeader } from "@/components/shell/AppHeader";
import { Button } from "@/components/ui/button";
import { FilterChipRow } from "@/components/common/FilterChipRow";
import { Pagination } from "@/components/common/Pagination";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Select } from "@/components/ui/select";
import { JobCard } from "@/components/job/JobCard";
import { ChannelOverview } from "@/components/channel/ChannelOverview";
import { useJobs, DEFAULT_FILTERS } from "@/hooks/useJobs";
import { useScrapedSummary } from "@/hooks/useScrapedSummary";
import { cn } from "@/lib/utils";

const TECH_OPTIONS_BASE = [
  { value: "", label: "全部技术栈" },
  { value: "java", label: "Java" },
  { value: "nodejs", label: "Node.js" },
  { value: "python", label: "Python" },
  { value: "agent", label: "AI Agent" },
  { value: "golang", label: "Go" },
  { value: "rust", label: "Rust" },
  { value: "llm", label: "LLM" },
];

const SORT_OPTIONS = [
  { value: "value", label: "价值观" },
  { value: "match", label: "匹配度" },
  { value: "posted", label: "发布时间" },
  { value: "salary", label: "薪资" },
];

export function Data() {
  const navigate = useNavigate();
  const location = useLocation();
  const [filters, setFilters] = React.useState(DEFAULT_FILTERS);
  const { data, loading, error } = useJobs(filters);
  const { data: summary } = useScrapedSummary();

  const techOptions = React.useMemo(
    () => TECH_OPTIONS_BASE.map((option) => ({
      ...option,
      label: `${option.label} (${option.value ? (summary?.tech_counts?.[option.value] ?? 0) : (summary?.total ?? 0)})`,
    })),
    [summary],
  );

  const preferenceOptions = React.useMemo(
    () => [{ value: "", label: "全部偏好" }, ...(summary?.preference_counts ?? []).map((p) => ({ value: p.key, label: `${p.label} (${p.count})` }))],
    [summary],
  );

  const totalPages = data ? Math.max(1, Math.ceil(data.total / filters.pageSize)) : 1;

  return (
    <>
      <AppHeader
        title="数据"
        subtitle={data ? `共 ${data.total} 条` : "职位库"}
        live
        action={
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => navigate("/jobs/new", { state: { backgroundLocation: location } })}
          >
            <Plus size={13} />
            添加职位
          </Button>
        }
      />
      <div className="flex flex-col gap-3 px-4">
        <ChannelOverview
          value={filters.channel}
          onChange={(channel) => setFilters((current) => ({ ...current, channel, page: 1 }))}
        />

        <FilterChipRow
          options={techOptions}
          value={filters.tag}
          onChange={(tag) => setFilters((f) => ({ ...f, tag, page: 1 }))}
        />
        <FilterChipRow
          options={preferenceOptions}
          value={filters.preference}
          onChange={(preference) => setFilters((f) => ({ ...f, preference, page: 1 }))}
        />
        <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 [scrollbar-width:none]">
          {([
            { on: filters.remote === true, label: "远程", toggle: () => setFilters((f) => ({ ...f, remote: f.remote ? null : true, page: 1 })) },
            { on: filters.valueTag === "低英语要求", label: "低英语要求", toggle: () => setFilters((f) => ({ ...f, valueTag: f.valueTag ? "" : "低英语要求", page: 1 })) },
            { on: filters.china, label: "居家可应聘", toggle: () => setFilters((f) => ({ ...f, china: !f.china, page: 1 })) },
          ] as const).map((chip) => (
            <button
              key={chip.label}
              type="button"
              onClick={chip.toggle}
              className={cn(
                "shrink-0 whitespace-nowrap border px-2.5 py-1.5 font-mono text-[11px] uppercase tracking-wide transition-colors",
                chip.on
                  ? "border-primary bg-primary text-primary-foreground font-semibold"
                  : "border-border-strong text-muted-foreground hover:text-foreground",
              )}
            >
              {chip.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <Select
            value={filters.sort}
            onChange={(e) => setFilters((f) => ({ ...f, sort: e.target.value as typeof f.sort, page: 1 }))}
            className="flex-1"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                按{o.label}排序
              </option>
            ))}
          </Select>
          <Button
            variant="outline"
            size="icon"
            onClick={() => setFilters((f) => ({ ...f, order: f.order === "desc" ? "asc" : "desc", page: 1 }))}
            aria-label="切换排序方向"
          >
            {filters.order === "desc" ? <ArrowDownWideNarrow size={16} /> : <ArrowUpWideNarrow size={16} />}
          </Button>
        </div>

        {loading && !data && (
          <div className="flex flex-col gap-3">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-36 w-full" />
            ))}
          </div>
        )}

        {error && <EmptyState message={`加载失败：${error}`} />}

        {!error && data && data.jobs.length === 0 && !loading && <EmptyState message="没有符合条件的职位" />}

        {!error &&
          data?.jobs.map((job) => (
            <JobCard
              key={job.id}
              variant="list"
              job={{
                id: job.id,
                channel: job.channel,
                external_id: job.external_id,
                title: job.title,
                company: job.company,
                salary: job.salary,
                salary_cny: job.salary_cny,
                city: job.city,
                skills: job.skills,
                url: job.url,
                sourceLabel: job.source_label,
                isRemote: job.is_remote,
                matchScore: job.match_score,
                valueScore: job.value_score,
                postedAt: job.posted_at,
                interestTags: job.interest_tags,
                valueTags: job.value_tags,
              }}
            />
          ))}

        {data && (
          <Pagination page={filters.page} totalPages={totalPages} onPageChange={(page) => setFilters((f) => ({ ...f, page }))} />
        )}
      </div>
    </>
  );
}
