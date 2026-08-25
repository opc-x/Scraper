import * as React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { displayField } from "@/lib/format";
import type { InterestTag, ValueTagHit } from "@/lib/types";
import { hitSeverity, SEVERITY_BADGE_VARIANT } from "@/lib/valueTagSeverity";
import { cn } from "@/lib/utils";

interface TagChipRowProps {
  channel: string;
  sourceLabel?: string;
  skills: string[];
  isRemote: boolean;
  city: string;
  interestTags: InterestTag[];
  valueTags?: ValueTagHit[];
  max?: number;
}

export function TagChipRow({ channel, sourceLabel, skills, isRemote, city, interestTags, valueTags = [], max = 5 }: TagChipRowProps) {
  const [expanded, setExpanded] = React.useState(false);
  const [overflowing, setOverflowing] = React.useState(false);
  const rowRef = React.useRef<HTMLDivElement>(null);
  const cityLabel = displayField(city);
  const cityIsGenericRemote = /^remote$/i.test(cityLabel);
  const extraInterestTags = interestTags.filter((t) => t.key !== "remote");
  const interestLabels = new Set(extraInterestTags.map((t) => t.label.toLowerCase()));
  const extraSkills = skills.filter((s) => !interestLabels.has(s.toLowerCase()));

  React.useLayoutEffect(() => {
    const row = rowRef.current;
    if (!row) return;
    const measure = () => setOverflowing(row.scrollHeight > 26);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(row);
    return () => observer.disconnect();
  }, [channel, sourceLabel, skills, interestTags, valueTags]);

  return (
    <div>
      <div
        ref={rowRef}
        className={cn(
          "flex flex-wrap items-center gap-1.5 overflow-hidden transition-[max-height] [&>*]:shrink-0",
          expanded ? "max-h-none" : "max-h-[26px]",
        )}
      >
      <Badge variant="outline" className="text-muted-foreground">
        {channel}
      </Badge>
      {sourceLabel && sourceLabel.toLowerCase() !== channel.toLowerCase() && (
        <Badge variant="info" title="来源 server / 频道">
          {sourceLabel}
        </Badge>
      )}
      {isRemote && (
        <Badge variant="default" className="bg-primary/15 text-primary">
          远程
        </Badge>
      )}
      {cityLabel && !cityIsGenericRemote && (
        <Badge variant="outline" className="text-muted-foreground">
          {cityLabel}
        </Badge>
      )}
      {extraInterestTags.slice(0, 2).map((tag) => (
        <Badge key={tag.key} variant="info" title={tag.label}>
          {tag.label}
        </Badge>
      ))}
      {extraSkills.slice(0, max).map((skill) => (
        <Badge key={skill} variant="secondary">
          {skill}
        </Badge>
      ))}
      {valueTags.filter((tag) => tag.matched).map((tag) => {
        const severity = hitSeverity(tag.polarity, tag.matched);
        return (
          <Badge key={tag.id} variant={SEVERITY_BADGE_VARIANT[severity]} title={tag.matched ? tag.evidence : `未命中「${tag.label}」`}>
            {tag.label}
          </Badge>
        );
      })}
      </div>
      {overflowing && (
        <button
          type="button"
          className="mt-1.5 flex items-center gap-1 font-mono text-[10px] text-muted-foreground hover:text-foreground"
          onClick={(event) => {
            event.stopPropagation();
            setExpanded((value) => !value);
          }}
        >
          {expanded ? "收起" : "展开"}
          {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
        </button>
      )}
    </div>
  );
}
