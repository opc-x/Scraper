import { useNavigate, useLocation } from "react-router-dom";
import { Star, Archive, ChevronRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { ScoreBadge } from "@/components/job/ScoreBadge";
import { TagChipRow } from "@/components/job/TagChipRow";
import { OriginButton } from "@/components/job/OriginButton";
import { useMarks } from "@/contexts/MarksProvider";
import { displayField, formatRelativeTime } from "@/lib/format";
import type { InterestTag, ValueTagHit } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface JobCardData {
  id: number;
  channel: string;
  external_id: string;
  title: string;
  company: string;
  salary: string;
  salary_cny?: string;
  city: string;
  skills: string[];
  url?: string;
  sourceLabel?: string;
  isRemote?: boolean;
  matchScore?: number;
  valueScore?: number;
  postedAt?: string | null;
  interestTags?: InterestTag[];
  valueTags?: ValueTagHit[];
}

interface JobCardProps {
  job: JobCardData;
  variant: "list" | "saved" | "archived";
}

export function JobCard({ job, variant }: JobCardProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { isSaved, isArchived, toggleSave, toggleArchive } = useMarks();

  const target = { id: job.id, channel: job.channel, external_id: job.external_id };
  const saved = isSaved(target);
  const archived = isArchived(target);
  const hasDetail = job.id > 0;
  if (variant === "list" && archived) return null;
  const company = displayField(job.company);
  const scored = job.matchScore !== undefined && job.matchScore >= 0;
  const hasValue = job.valueScore !== undefined;
  const posted = formatRelativeTime(job.postedAt);

  const openDetail = () => {
    if (!hasDetail) return;
    navigate(`/jobs/${job.id}`, { state: { backgroundLocation: location } });
  };

  return (
    <Card className="overflow-hidden">
      <div
        onClick={openDetail}
        className={cn(
          "flex w-full flex-col gap-2.5 p-4 text-left transition-colors active:bg-card-foreground/5",
          hasDetail ? "cursor-pointer" : "cursor-default",
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex flex-col gap-0.5">
            {company ? (
              <p className="truncate font-mono text-[11px] uppercase tracking-wider text-muted-foreground">{company}</p>
            ) : null}
            {posted ? (
              <p className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground-dim">{posted}</p>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {hasValue && (
              <span className="font-mono text-[11px] text-muted-foreground" title="价值观分">
                V{job.valueScore}
              </span>
            )}
            {scored && <ScoreBadge score={job.matchScore!} />}
          </div>
        </div>
        <h3 className="font-heading text-[15px] font-bold leading-snug text-foreground">{job.title}</h3>
        {(job.salary_cny || job.salary) && (
          <div className="flex flex-col gap-0.5">
            {job.salary_cny ? (
              <p className="font-mono text-[13px] font-semibold text-primary">{job.salary_cny}</p>
            ) : null}
            {job.salary ? (
              <p className={cn("font-mono text-[12px]", job.salary_cny ? "text-muted-foreground" : "text-foreground/85")}>
                {job.salary}
              </p>
            ) : null}
          </div>
        )}
        <TagChipRow
          channel={job.channel}
          sourceLabel={job.sourceLabel}
          skills={job.skills}
          isRemote={!!job.isRemote}
          city={job.city}
          interestTags={job.interestTags ?? []}
          valueTags={job.valueTags ?? []}
        />
        {!hasDetail && <p className="text-xs text-muted-foreground">原职位已从库中移除，仅保留快照信息</p>}
      </div>
      <div className="flex items-center gap-4 border-t border-border px-4 py-2.5">
        <button
          type="button"
          onClick={() => toggleSave(target)}
          className={cn("flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground", saved && "text-primary hover:text-primary")}
        >
          <Star size={13} fill={saved ? "currentColor" : "none"} />
          {saved ? "已收藏" : "收藏"}
        </button>
        <button
          type="button"
          onClick={() => toggleArchive(target)}
          className={cn("flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground", archived && "text-foreground/80")}
        >
          <Archive size={13} fill={archived ? "currentColor" : "none"} />
          {archived ? (variant === "archived" ? "取消归档" : "已归档") : "归档"}
        </button>
        <OriginButton
          job={{ channel: job.channel, external_id: job.external_id, url: job.url || "" }}
          className="ml-auto font-mono text-[10px] uppercase tracking-wide text-primary"
        />
        {hasDetail && (
          <button
            type="button"
            className="flex items-center gap-0.5 font-mono text-[10px] uppercase tracking-wide text-muted-foreground-dim hover:text-foreground"
            onClick={openDetail}
          >
            详情 <ChevronRight size={12} />
          </button>
        )}
      </div>
    </Card>
  );
}
