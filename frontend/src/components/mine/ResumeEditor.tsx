import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { Resume } from "@/lib/types";

type Pane = "original" | "final";

interface ResumeEditorProps {
  open: boolean;
  pane: Pane;
  resume: Resume | null;
  markdown: string;
  finalMarkdown: string;
  saving: boolean;
  onOpenChange: (open: boolean) => void;
  onPane: (pane: Pane) => void;
  onTitle: (title: string) => void;
  onMarkdown: (markdown: string) => void;
  onSave: () => void;
}

export function ResumeEditor({
  open,
  pane,
  resume,
  markdown,
  finalMarkdown,
  saving,
  onOpenChange,
  onPane,
  onTitle,
  onMarkdown,
  onSave,
}: ResumeEditorProps) {
  const text = pane === "original" ? markdown : finalMarkdown;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <div
          className="flex items-center justify-between border-b border-border px-4 pb-3"
          style={{ paddingTop: "calc(14px + env(safe-area-inset-top, 0px))" }}
        >
          <DialogTitle className="font-heading text-base font-semibold">简历</DialogTitle>
          <Button variant="ghost" size="icon-sm" onClick={() => onOpenChange(false)} aria-label="关闭">
            <X size={16} />
          </Button>
        </div>
        <div className="flex flex-col gap-3 px-4 py-4">
          <Input
            value={resume?.title ?? ""}
            onChange={(e) => onTitle(e.target.value)}
            placeholder="简历标题"
          />
          <div className="flex border border-border">
            <button
              type="button"
              onClick={() => onPane("original")}
              className={cn(
                "flex-1 py-2 font-mono text-[11px] uppercase tracking-wide",
                pane === "original" ? "bg-primary text-primary-foreground font-semibold" : "text-muted-foreground",
              )}
            >
              原稿
            </button>
            <button
              type="button"
              onClick={() => onPane("final")}
              className={cn(
                "flex-1 border-l border-border py-2 font-mono text-[11px] uppercase tracking-wide",
                pane === "final" ? "bg-primary text-primary-foreground font-semibold" : "text-muted-foreground",
              )}
            >
              当前版本
            </button>
          </div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">
            {pane === "original" ? "上传 / 手改的底稿 · AI 不能覆盖" : "采纳建议后落下的当前版 · 原稿不动"}
            {` · ${text.length} 字`}
          </p>
          {pane === "final" && !finalMarkdown ? (
            <div className="flex min-h-[40vh] items-center justify-center border border-border text-[13px] text-muted-foreground">
              还没有版本
            </div>
          ) : (
            <textarea
              value={text}
              readOnly={pane === "final"}
              onChange={(e) => pane === "original" && onMarkdown(e.target.value)}
              spellCheck={false}
              className="min-h-[50vh] w-full resize-y border border-input bg-card/60 px-3.5 py-3 font-mono text-[13px] leading-relaxed text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring read-only:text-muted-foreground"
            />
          )}
          {pane === "original" && (
            <Button className="w-full" disabled={saving || !resume} onClick={onSave}>
              {saving ? "保存中" : "保存原稿"}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
