import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { openOrigin, type OriginJob } from "@/lib/openOrigin";
import { cn } from "@/lib/utils";

interface OriginButtonProps {
  job: OriginJob;
  className?: string;
  fullWidth?: boolean;
}

export function OriginButton({ job, className, fullWidth }: OriginButtonProps) {
  if (!job.url && !(job.channel === "boss" && job.external_id)) return null;
  return (
    <Button
      type="button"
      variant={fullWidth ? "outline" : "ghost"}
      size={fullWidth ? "default" : "sm"}
      className={cn(fullWidth && "w-full", className)}
      onClick={(event) => {
        event.stopPropagation();
        openOrigin(job);
      }}
    >
      <ExternalLink size={15} />
      原文
    </Button>
  );
}
