import * as React from "react";
import { Sparkles, X } from "lucide-react";
import { apiPost, ApiError } from "@/lib/api";
import type { ValueTagLibraryEntry } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { hitSeverity, SEVERITY_BADGE_VARIANT } from "@/lib/valueTagSeverity";

interface ValueTagPickerProps {
  jobId: number;
  library: ValueTagLibraryEntry[];
  onChanged: () => void;
}

interface AiTagResult {
  applied: { id: number; label: string }[];
  skipped: { id: number; label: string }[];
}

function TagSection({
  title,
  tags,
  removable,
  pending,
  onRemove,
}: {
  title: string;
  tags: ValueTagLibraryEntry[];
  removable: boolean;
  pending: number | null;
  onRemove: (tag: ValueTagLibraryEntry, on: boolean) => Promise<void>;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <p className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground-dim">{title}</p>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag) => {
          const severity = hitSeverity(tag.polarity, true);
          return removable ? (
            <button
              key={tag.id}
              type="button"
              disabled={pending === tag.id}
              onClick={() => void onRemove(tag, false)}
              className="disabled:opacity-50"
              title={`取消「${tag.label}」`}
            >
              <Badge variant={SEVERITY_BADGE_VARIANT[severity]}>
                {tag.label} <X size={10} />
              </Badge>
            </button>
          ) : (
            <Badge key={tag.id} variant={SEVERITY_BADGE_VARIANT[severity]} title="规则自动命中">
              {tag.label}
            </Badge>
          );
        })}
      </div>
    </div>
  );
}

export function ValueTagPicker({ jobId, library, onChanged }: ValueTagPickerProps) {
  const toast = useToast();
  const [pending, setPending] = React.useState<number | null>(null);
  const [open, setOpen] = React.useState(false);
  const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  const buckets = React.useMemo(() => {
    const matched = library.filter((tag) => tag.matched ?? tag.applied);
    return {
      rule: matched.filter((tag) => tag.auto),
      ingest: matched.filter((tag) => !tag.auto && tag.source === "ai_ingest"),
      assist: matched.filter((tag) => !tag.auto && tag.source !== "ai_ingest"),
    };
  }, [library]);

  const setManual = async (tag: ValueTagLibraryEntry, on: boolean) => {
    if (tag.auto && !on && !tag.manual) return;
    setPending(tag.id);
    try {
      await apiPost(`/api/jobs/${jobId}/value-tags/${tag.id}`, { on });
      onChanged();
    } finally {
      setPending(null);
    }
  };

  const runAi = async () => {
    const text = note.trim();
    if (!text) {
      toast("先写一句再打标", "error");
      return;
    }
    setBusy(true);
    try {
      const result = await apiPost<AiTagResult>(`/api/jobs/${jobId}/ai-tag`, { message: text });
      if (result.applied.length > 0) {
        toast(`打标成功：${result.applied.map((t) => t.label).join("、")}`, "success");
        setNote("");
        setOpen(false);
        onChanged();
      } else if (result.skipped.length > 0) {
        toast(`已经打过：${result.skipped.map((t) => t.label).join("、")}`);
        setOpen(false);
      } else {
        toast("扯犊子，没打上标签", "error");
      }
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "打标失败，再试一次", "error");
    } finally {
      setBusy(false);
    }
  };

  if (library.length === 0) return null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">职位标签</p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">自动结果只读；AI 推理补标可以取消。</p>
        </div>
        <Button type="button" size="sm" variant="outline" className="shrink-0 gap-1 text-info" onClick={() => setOpen(true)}>
          <Sparkles size={13} />
          AI 打标
        </Button>
      </div>
      {buckets.rule.length > 0 && (
        <TagSection title="标签规则命中" tags={buckets.rule} removable={false} pending={pending} onRemove={setManual} />
      )}
      {buckets.ingest.length > 0 && (
        <TagSection title="录入 AI 自动打标" tags={buckets.ingest} removable={false} pending={pending} onRemove={setManual} />
      )}
      {buckets.assist.length > 0 && (
        <TagSection title="AI 推理补标" tags={buckets.assist} removable pending={pending} onRemove={setManual} />
      )}

      <Dialog open={open} onOpenChange={(next) => !busy && setOpen(next)}>
        <DialogContent className="p-4">
          <DialogTitle className="mb-4 font-heading text-lg font-semibold">AI 推理打标</DialogTitle>
          <p className="mb-3 text-xs leading-relaxed text-muted-foreground">
            写你对这条职位的判断。AI 对照职位原文匹配已有标签，对不上就打不上。
          </p>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            disabled={busy}
            rows={4}
            placeholder="比如：JD 写了大小周，开会也多"
            className="w-full resize-none rounded-[var(--radius-md)] border border-input bg-card/60 px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          />
          <Button type="button" className="mt-3 w-full gap-1.5" disabled={busy} onClick={() => void runAi()}>
            {busy ? "识别中…" : (
              <>
                <Sparkles size={14} />
                开始打标
              </>
            )}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
