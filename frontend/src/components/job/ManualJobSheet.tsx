import * as React from "react";
import { useNavigate } from "react-router-dom";
import { X, Loader2, Sparkles, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { apiPost, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

type Mode = "text" | "url" | "markdown";

const MODES: { id: Mode; label: string }[] = [
  { id: "text", label: "粘贴文本" },
  { id: "url", label: "职位链接" },
  { id: "markdown", label: "MD 批量" },
];

const HINTS: Record<Mode, string> = {
  text: "把单条职位描述原文粘贴进去，后台 AI 结构化 + 对照简历打分后入库。",
  url: "贴职位链接。能打开就抓正文处理；打不开会明确告诉你，改贴原文或用 MD 批量。",
  markdown: "上传或粘贴 Markdown。多条职位用单独一行的 --- 分隔，一次最多 15 条。",
};

function apiDetail(e: unknown): string {
  if (!(e instanceof ApiError)) return "解析失败，请重试";
  try {
    const j = JSON.parse(e.message) as { detail?: unknown };
    if (typeof j.detail === "string") return j.detail;
  } catch {
    /* raw text */
  }
  return e.message || "解析失败，请重试";
}

function countMarkdownChunks(text: string): number {
  const parts = text.split(/^\s*-{3,}\s*$/m).map((p) => p.trim()).filter(Boolean);
  return parts.length;
}

type ManualResult = {
  id: number;
  ids: number[];
  ok: number;
  failed: { index: number; error: string }[];
  total?: number;
};

export function ManualJobSheet() {
  const navigate = useNavigate();
  const toast = useToast();
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [mode, setMode] = React.useState<Mode>("text");
  const [content, setContent] = React.useState("");
  const [fileName, setFileName] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  const close = () => navigate(-1);
  const chunkCount = mode === "markdown" && content.trim() ? countMarkdownChunks(content) : 0;
  const canSubmit = mode === "url" ? /^https?:\/\//i.test(content.trim()) : !!content.trim();

  const onPickFile = async (file: File | null) => {
    if (!file) return;
    const text = await file.text();
    setContent(text);
    setFileName(file.name);
    setMode("markdown");
  };

  const submit = async () => {
    if (!canSubmit || submitting) return;
    setSubmitting(true);
    try {
      const result = await apiPost<ManualResult>("/api/jobs/manual", {
        mode,
        content: content.trim(),
      });
      const failedN = result.failed?.length ?? 0;
      if (mode === "markdown" && (result.ok > 1 || failedN > 0)) {
        toast(
          failedN
            ? `入库 ${result.ok} 条，失败 ${failedN} 条`
            : `已批量入库 ${result.ok} 条`,
          failedN ? "error" : "success",
        );
      } else {
        toast("已解析并存入职位库", "success");
      }
      navigate(`/jobs/${result.id}`, { replace: true });
    } catch (e) {
      toast(apiDetail(e), "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60">
      <div
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex h-full w-full flex-col overflow-y-auto bg-background",
          "sm:max-w-lg sm:border-l sm:border-border",
        )}
      >
        <div
          className="flex items-center justify-between border-b border-border px-4 pb-3"
          style={{ paddingTop: "calc(14px + env(safe-area-inset-top, 0px))" }}
        >
          <h1 className="font-heading text-base font-semibold">添加职位</h1>
          <Button variant="ghost" size="icon-sm" onClick={close} aria-label="关闭">
            <X size={16} />
          </Button>
        </div>

        <div className="flex flex-col gap-3 px-4 py-4">
          <p className="text-[13px] leading-relaxed text-muted-foreground">{HINTS[mode]}</p>

          <div className="flex gap-1.5">
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setMode(m.id)}
                className={cn(
                  "flex-1 border py-1.5 font-mono text-[11px] uppercase tracking-wide",
                  mode === m.id
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground",
                )}
              >
                {m.label}
              </button>
            ))}
          </div>

          {mode === "markdown" && (
            <div className="flex items-center gap-2">
              <input
                ref={fileRef}
                type="file"
                accept=".md,.markdown,text/markdown,text/plain"
                className="hidden"
                onChange={(e) => onPickFile(e.target.files?.[0] ?? null)}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => fileRef.current?.click()}
              >
                <Upload size={14} />
                选 Markdown 文件
              </Button>
              {fileName && (
                <span className="truncate font-mono text-[11px] text-muted-foreground">{fileName}</span>
              )}
              {chunkCount > 0 && (
                <span className="shrink-0 font-mono text-[11px] text-primary">{chunkCount} 条</span>
              )}
            </div>
          )}

          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={
              mode === "text"
                ? "把职位描述原文粘贴到这里"
                : mode === "url"
                  ? "https://..."
                  : "粘贴 Markdown，或上方选文件。多条之间用单独一行的 --- 分隔"
            }
            className={cn(
              "w-full resize-y border border-input bg-card/60 px-3 py-2 text-[13px] leading-relaxed text-foreground outline-none",
              mode === "url" ? "min-h-14" : "min-h-56",
            )}
          />

          <Button onClick={submit} disabled={!canSubmit || submitting} className="gap-2">
            {submitting ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {submitting
              ? mode === "markdown"
                ? "批量解析中…"
                : "AI 解析中…"
              : mode === "markdown"
                ? "批量解析并保存"
                : "AI 解析并保存"}
          </Button>
        </div>
      </div>
    </div>
  );
}
