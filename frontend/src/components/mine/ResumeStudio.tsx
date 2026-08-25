import * as React from "react";
import { Check, ChevronDown, Eye, FileText, Pencil, Search, Sparkles, Trash2, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Resume, ResumeAnalysis, ResumeModelId, ResumeVersion } from "@/lib/types";
import { useResumes } from "@/hooks/useResumes";
import { useResumeLoop } from "@/hooks/useResumeLoop";
import { useSops } from "@/hooks/useSops";
import { ResumeEditor } from "@/components/mine/ResumeEditor";
import { MODELS, SopFlow } from "@/components/mine/TrioBoard";

const ACCEPT_ATTR = ".pdf,.doc,.docx,.md,.markdown";
const MAX_BYTES = 8 * 1024 * 1024;
const MODEL_NAME: Record<string, string> = { claude: "Claude", codex: "Codex", cursor: "Cursor" };
const STATUS_NAME: Record<string, string> = { pending: "待定", adopted: "采纳", rejected: "不采纳" };
const STEPS = [
  { id: 1 as const, label: "上传" },
  { id: 2 as const, label: "分析" },
  { id: 3 as const, label: "优化" },
];

type StepId = 1 | 2 | 3;

function formatWhen(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function errText(err: unknown, fallback: string) {
  if (err instanceof ApiError && err.message) {
    try {
      const parsed = JSON.parse(err.message) as { detail?: string };
      if (parsed.detail) return parsed.detail;
    } catch {
      return err.message;
    }
  }
  return fallback;
}

export function ResumeStudio() {
  const toast = useToast();
  const inputRef = React.useRef<HTMLInputElement>(null);
  const stepped = React.useRef(false);
  const { rows, loading, upload, replaceOriginal, update, activate, remove, get, reload } = useResumes();
  const sops = useSops();
  const [step, setStep] = React.useState<StepId>(1);
  const [replaceId, setReplaceId] = React.useState<number | null>(null);
  const [dragging, setDragging] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [confirmResume, setConfirmResume] = React.useState<number | null>(null);
  const [confirmSop, setConfirmSop] = React.useState<number | null>(null);
  const [confirmVersion, setConfirmVersion] = React.useState<number | null>(null);
  const [editing, setEditing] = React.useState<Resume | null>(null);
  const [pane, setPane] = React.useState<"original" | "final">("original");
  const [draftTitle, setDraftTitle] = React.useState("");
  const [draftMd, setDraftMd] = React.useState("");
  const [draftFinal, setDraftFinal] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [sopBrief, setSopBrief] = React.useState("");
  const [sopModels, setSopModels] = React.useState<ResumeModelId[]>(["codex", "cursor", "claude"]);
  const [generating, setGenerating] = React.useState(false);
  const [sopsOpen, setSopsOpen] = React.useState(false);
  const [pickedSopId, setPickedSopId] = React.useState<number | null>(null);
  const [asking, setAsking] = React.useState(false);
  const [analyzing, setAnalyzing] = React.useState(false);
  const [applying, setApplying] = React.useState(false);
  const [viewing, setViewing] = React.useState<ResumeVersion | null>(null);
  const [reportsOpen, setReportsOpen] = React.useState(false);
  const [viewingReport, setViewingReport] = React.useState<ResumeAnalysis | null>(null);
  const [confirmAnalysis, setConfirmAnalysis] = React.useState<number | null>(null);
  const [renameTitle, setRenameTitle] = React.useState("");
  const [renaming, setRenaming] = React.useState(false);
  const [reportId, setReportId] = React.useState<number | null>(null);
  const [brief, setBrief] = React.useState("");
  const [optModels, setOptModels] = React.useState<ResumeModelId[]>(["codex", "cursor", "claude"]);
  const [optSopsOpen, setOptSopsOpen] = React.useState(false);
  const [pickedOptSopId, setPickedOptSopId] = React.useState<number | null>(null);
  const [analyzeOpen, setAnalyzeOpen] = React.useState(false);
  const [askOpen, setAskOpen] = React.useState(false);
  const [versionsOpen, setVersionsOpen] = React.useState(false);

  const active = rows.find((r) => r.is_active) ?? rows[0] ?? null;
  const scoped = sops.books.filter((b) => b.resume_id == null || b.resume_id === active?.id);
  const mineSops = scoped.filter((b) => (b.purpose || "analyze") === "analyze");
  const optSops = scoped.filter((b) => b.purpose === "optimize");
  const playbook = sops.draft("analyze");
  const picked = mineSops.find((b) => b.id === pickedSopId) ?? mineSops[0] ?? null;
  const pickedOpt = optSops.find((b) => b.id === pickedOptSopId) ?? optSops[0] ?? null;
  const loop = useResumeLoop(active?.id ?? null);
  React.useEffect(() => {
    if (reportId != null && loop.analyses.some((a) => a.id === reportId)) return;
    setReportId(loop.analyses[0]?.id ?? null);
  }, [loop.analyses, reportId]);

  React.useEffect(() => {
    if (pickedSopId != null && mineSops.some((b) => b.id === pickedSopId)) return;
    setPickedSopId(mineSops[0]?.id ?? null);
  }, [mineSops, pickedSopId]);

  React.useEffect(() => {
    if (pickedOptSopId != null && optSops.some((b) => b.id === pickedOptSopId)) return;
    setPickedOptSopId(optSops[0]?.id ?? null);
  }, [optSops, pickedOptSopId]);

  React.useEffect(() => {
    if (!playbook) return;
    if (playbook.brief) setSopBrief(playbook.brief);
    if (playbook.models?.length) setSopModels(playbook.models);
  }, [playbook?.id, playbook?.updated_at]);

  const pending = loop.suggestions.filter((s) => s.status === "pending");
  const adopted = loop.suggestions.filter((s) => s.status === "adopted");
  const rejected = loop.suggestions.filter((s) => s.status === "rejected");
  const orderedVersions = [
    ...loop.versions.filter((v) => v.is_current),
    ...loop.versions.filter((v) => !v.is_current),
  ];
  const shownVersions = versionsOpen ? orderedVersions : orderedVersions.slice(0, 1);

  React.useEffect(() => {
    if (stepped.current || loading || loop.loading) return;
    stepped.current = true;
    const q = Number(new URLSearchParams(window.location.search).get("step"));
    if (q === 1 || q === 2 || q === 3) {
      setStep(q);
      return;
    }
    if (!active) setStep(1);
    else setStep(1);
  }, [loading, loop.loading, active]);

  const openFile = (id: number | null) => {
    setReplaceId(id);
    inputRef.current?.click();
  };

  const pick = async (raw: File | undefined) => {
    if (!raw || busy) return;
    if (raw.size > MAX_BYTES) {
      toast("文件超过 8MB", "error");
      return;
    }
    setBusy(true);
    try {
      if (replaceId != null) {
        await replaceOriginal(replaceId, raw);
        toast("原稿已替换", "success");
      } else {
        await upload(raw);
        toast("原稿已入库", "success");
      }
    } catch (err) {
      toast(errText(err, "上传失败"), "error");
    } finally {
      setBusy(false);
      setReplaceId(null);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    setReplaceId(null);
    void pick(e.dataTransfer.files[0]);
  };

  const openEdit = async (id: number, nextPane: "original" | "final" = "original") => {
    try {
      const row = await get(id);
      setEditing(row);
      setPane(nextPane);
      setDraftTitle(row.title);
      setDraftMd(row.markdown ?? "");
      setDraftFinal(row.final_markdown ?? "");
    } catch (err) {
      toast(errText(err, "打不开这份简历"), "error");
    }
  };

  const onSave = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      await update(editing.id, { title: draftTitle || editing.title, markdown: draftMd });
      toast("原稿已保存", "success");
      setEditing(null);
    } catch (err) {
      toast(errText(err, "保存失败"), "error");
    } finally {
      setSaving(false);
    }
  };

  const onDeleteResume = async (id: number) => {
    if (confirmResume !== id) {
      setConfirmResume(id);
      return;
    }
    try {
      await remove(id);
      setConfirmResume(null);
      toast("已删除", "success");
      setStep(1);
    } catch (err) {
      toast(errText(err, "删除失败"), "error");
    }
  };

  const onDeleteSop = async (id: number) => {
    if (confirmSop !== id) {
      setConfirmSop(id);
      return;
    }
    try {
      await sops.remove(id);
      setConfirmSop(null);
      toast("SOP 已删", "success");
    } catch (err) {
      toast(errText(err, "删除失败"), "error");
    }
  };

  const toggleSopModel = (id: ResumeModelId) => {
    setSopModels((prev) => {
      if (prev.includes(id)) return prev.length === 1 ? prev : prev.filter((x) => x !== id);
      return [...prev, id];
    });
  };

  const generateSop = async () => {
    if (!sopBrief.trim()) {
      toast("先写你要怎么审", "error");
      return;
    }
    if (sopModels.length === 0) {
      toast("至少选一个模型", "error");
      return;
    }
    setGenerating(true);
    try {
      const row = await sops.generate({
        brief: sopBrief.trim(),
        models: sopModels,
        resumeId: active?.id,
        purpose: "analyze",
      });
      setPickedSopId(row.id);
      toast("流程图出来了", "success");
    } catch (err) {
      toast(errText(err, "生成失败"), "error");
    } finally {
      setGenerating(false);
    }
  };

  const finishReport = async (row: Awaited<ReturnType<typeof loop.analyze>>) => {
    sops.reload();
    setAnalyzeOpen(false);
    toast("报告已生成", "success");
    if (row) {
      const full = row.findings ? row : await loop.getAnalysis(row.id);
      setViewingReport(full);
      setRenameTitle(full.title);
    }
  };

  const runDirect = async () => {
    if (!active) {
      toast("先上传一份原稿", "error");
      setStep(1);
      return;
    }
    if (!sopBrief.trim()) {
      toast("先写你要怎么审", "error");
      return;
    }
    setAnalyzing(true);
    try {
      const row = await loop.analyze(null, {
        brief: sopBrief.trim(),
        models: sopModels,
        direct: true,
      });
      await finishReport(row);
    } catch (err) {
      toast(errText(err, "分析失败"), "error");
    } finally {
      setAnalyzing(false);
    }
  };

  const runAnalyze = async () => {
    if (!active) {
      toast("先上传一份原稿", "error");
      setStep(1);
      return;
    }
    if (!playbook || playbook.steps.length === 0) {
      toast("先出流程图，再按图分析", "error");
      return;
    }
    setAnalyzing(true);
    try {
      const row = await loop.analyze(playbook.id);
      await finishReport(row);
    } catch (err) {
      toast(errText(err, "分析失败"), "error");
    } finally {
      setAnalyzing(false);
    }
  };

  const toggleOptModel = (id: ResumeModelId) => {
    setOptModels((prev) => {
      if (prev.includes(id)) return prev.length === 1 ? prev : prev.filter((x) => x !== id);
      return [...prev, id];
    });
  };

  const ask = async (sopId?: number | null) => {
    if (!active) {
      toast("先上传一份原稿", "error");
      setStep(1);
      return;
    }
    if (!brief.trim()) {
      toast("先写你要怎么改", "error");
      return;
    }
    if (!reportId) {
      toast("先选一份分析报告", "error");
      return;
    }
    setAsking(true);
    try {
      await loop.suggest(optModels[0] ?? "claude", {
        analysisId: reportId,
        brief: brief.trim(),
        sopId: sopId ?? null,
      });
      sops.reload();
      toast("建议出来了，点采纳或不采纳", "success");
    } catch (err) {
      toast(errText(err, "出不了建议"), "error");
    } finally {
      setAsking(false);
    }
  };

  const generateOptSop = async () => {
    if (!brief.trim()) {
      toast("先写你要怎么改", "error");
      return;
    }
    if (!reportId) {
      toast("先选一份分析报告", "error");
      return;
    }
    setGenerating(true);
    try {
      const row = await sops.generate({
        brief: brief.trim(),
        models: optModels,
        resumeId: active?.id,
        purpose: "optimize",
      });
      setPickedOptSopId(row.id);
      toast("流程图出来了", "success");
    } catch (err) {
      toast(errText(err, "生成失败"), "error");
    } finally {
      setGenerating(false);
    }
  };

  const onSetStatus = async (id: number, status: "adopted" | "rejected") => {
    try {
      await loop.setStatus(id, status);
    } catch (err) {
      toast(errText(err, "改不了这条"), "error");
    }
  };

  const applyAdopted = async () => {
    setApplying(true);
    try {
      const ver = await loop.apply();
      await reload();
      setAskOpen(false);
      toast(ver ? `已落 v${ver.version}` : "已落新版本", "success");
    } catch (err) {
      toast(errText(err, "先采纳至少一条"), "error");
    } finally {
      setApplying(false);
    }
  };

  const onDeleteAnalysis = async (id: number) => {
    if (confirmAnalysis !== id) {
      setConfirmAnalysis(id);
      return;
    }
    try {
      await loop.removeAnalysis(id);
      setConfirmAnalysis(null);
      if (viewingReport?.id === id) setViewingReport(null);
      toast("报告已删", "success");
    } catch (err) {
      toast(errText(err, "删不掉"), "error");
    }
  };

  const onRenameReport = async () => {
    if (!viewingReport) return;
    const title = renameTitle.trim();
    if (!title) return;
    setRenaming(true);
    try {
      const row = await loop.renameAnalysis(viewingReport.id, title);
      if (row) setViewingReport({ ...viewingReport, ...row });
      toast("标题已改", "success");
    } catch (err) {
      toast(errText(err, "改不了"), "error");
    } finally {
      setRenaming(false);
    }
  };

  const onDeleteVersion = async (id: number) => {
    if (confirmVersion !== id) {
      setConfirmVersion(id);
      return;
    }
    try {
      await loop.remove(id);
      setConfirmVersion(null);
      if (viewing?.id === id) setViewing(null);
      await reload();
      toast("版本已删", "success");
    } catch (err) {
      toast(errText(err, "删不掉"), "error");
    }
  };

  const go = (next: StepId) => {
    if (next !== 1 && !active) {
      toast("先上传一份原稿", "error");
      setStep(1);
      return;
    }
    setStep(next);
  };

  const openAnalyze = () => {
    if (!active) {
      toast("先上传一份原稿", "error");
      setStep(1);
      return;
    }
    setStep(2);
    setAnalyzeOpen(true);
  };

  return (
    <div className="border border-border">
      <div className="flex items-center justify-between border-b border-border px-3.5 py-2.5">
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">简历工作室</span>
        <span className="font-mono text-[11px] text-primary">
          {active ? active.title : "还没有原稿"}
        </span>
      </div>

      <div className="grid grid-cols-3 border-b border-border">
        {STEPS.map((item) => {
          const on = step === item.id;
          const done =
            (item.id === 1 && !!active) ||
            (item.id === 2 && loop.analyses.length > 0) ||
            (item.id === 3 && loop.versions.length > 0);
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => go(item.id)}
              className={cn(
                "flex flex-col items-center gap-0.5 border-r border-border py-2 last:border-r-0 font-mono",
                on
                  ? "bg-primary text-primary-foreground font-semibold"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <span className="text-[10px] tracking-widest">{done && !on ? "✓" : item.id}</span>
              <span className="text-[11px] tracking-wide">{item.label}</span>
            </button>
          );
        })}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT_ATTR}
        className="hidden"
        onChange={(e) => {
          void pick(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      {step === 1 && (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(dragging && "bg-primary/10")}
        >
          {loading && (
            <div className="px-3.5 py-3">
              <Skeleton className="h-14 w-full" />
            </div>
          )}

          {!loading && rows.length === 0 && (
            <button
              type="button"
              onClick={() => openFile(null)}
              className="flex w-full flex-col items-center gap-2 px-3.5 py-7"
            >
              <Upload size={18} className={dragging ? "text-primary" : "text-muted-foreground"} />
              <p className="font-mono text-[12px] text-foreground">{dragging ? "松开即可入库" : "上传原稿"}</p>
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">
                PDF / Word / Markdown
              </p>
            </button>
          )}

          {!loading &&
            rows.map((row) => (
              <div
                key={row.id}
                className={cn(
                  "flex items-start gap-2 border-b border-border px-3.5 py-3 last:border-b-0",
                  row.is_active && "bg-primary/5",
                )}
              >
                <FileText size={16} className={cn("mt-0.5 shrink-0", row.is_active ? "text-primary" : "text-muted-foreground")} />
                <button type="button" onClick={() => void activate(row.id)} className="min-w-0 flex-1 text-left">
                  <p className="truncate font-mono text-[13px] font-semibold text-foreground">{row.title}</p>
                  <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                    {row.is_active ? "当前 · " : ""}
                    原稿 {row.chars} 字
                    {row.current_version ? ` · 当前 v${row.current_version}` : ""}
                    {row.updated_at ? ` · ${formatWhen(row.updated_at)}` : ""}
                  </p>
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => openFile(row.id)}
                  className="shrink-0 p-1 text-muted-foreground hover:text-foreground"
                  aria-label="上传替换原稿"
                >
                  <Upload size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => void openEdit(row.id, "original")}
                  className="shrink-0 p-1 text-muted-foreground hover:text-foreground"
                  aria-label="打开"
                >
                  <Pencil size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => void onDeleteResume(row.id)}
                  className={cn(
                    "shrink-0 p-1",
                    confirmResume === row.id ? "text-destructive" : "text-muted-foreground hover:text-foreground",
                  )}
                  aria-label="删除"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}

          {active && (
            <div className="grid grid-cols-2 gap-2 px-3.5 py-3">
              <Button variant="outline" onClick={openAnalyze}>
                去分析
              </Button>
              <Button onClick={() => go(3)}>
                去优化
              </Button>
            </div>
          )}
        </div>
      )}

      {step === 2 && (
        <div>
          {active ? (
            <p className="border-b border-border px-3.5 py-2 font-mono text-[11px] text-muted-foreground">
              审 {active.title} · {active.chars} 字 · 只出洞，不改稿
            </p>
          ) : (
            <p className="px-3.5 py-6 text-center text-[13px] text-muted-foreground">先上传一份原稿</p>
          )}

          <div className="border-b border-border px-3.5 py-3">
            <Button className="w-full" disabled={!active} onClick={openAnalyze}>
              <Search />
              去分析
            </Button>
          </div>

          <div className="border-t border-border">
            <div className="flex items-center justify-between px-3.5 py-2.5">
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">
                分析报告{loop.analyses.length ? ` · ${loop.analyses.length} 份` : ""}
              </span>
              {loop.analyses.length > 1 && (
                <button
                  type="button"
                  onClick={() => setReportsOpen((v) => !v)}
                  className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground hover:text-foreground"
                >
                  <ChevronDown size={12} className={cn(reportsOpen && "rotate-180")} />
                  {reportsOpen ? "收起" : `还有 ${loop.analyses.length - 1} 份`}
                </button>
              )}
            </div>
            {loop.analyses.length === 0 && (
              <p className="px-3.5 pb-4 text-center text-[13px] text-muted-foreground">
                还没有报告，点上面去分析
              </p>
            )}
            {(reportsOpen ? loop.analyses : loop.analyses.slice(0, 1)).map((row) => (
              <div
                key={row.id}
                className="flex items-start gap-2 border-t border-border px-3.5 py-3"
              >
                <button
                  type="button"
                  onClick={() => {
                    void loop.getAnalysis(row.id).then((full) => {
                      setViewingReport(full);
                      setRenameTitle(full.title);
                    });
                  }}
                  className="min-w-0 flex-1 text-left"
                >
                  <p className="truncate font-mono text-[13px] font-semibold text-foreground">{row.title}</p>
                  <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                    {row.finding_count} 条
                    {row.created_at ? ` · ${formatWhen(row.created_at)}` : ""}
                  </p>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    void loop.getAnalysis(row.id).then((full) => {
                      setViewingReport(full);
                      setRenameTitle(full.title);
                    });
                  }}
                  className="shrink-0 p-1 text-muted-foreground hover:text-foreground"
                  aria-label="查看报告"
                >
                  <Eye size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => void onDeleteAnalysis(row.id)}
                  className={cn(
                    "shrink-0 p-1",
                    confirmAnalysis === row.id ? "text-destructive" : "text-muted-foreground hover:text-foreground",
                  )}
                  aria-label="删除报告"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {step === 3 && (
        <div>
          {active ? (
            <p className="border-b border-border px-3.5 py-2 font-mono text-[11px] text-muted-foreground">
              {active.title}
              {active.current_version ? ` · 当前 v${active.current_version}` : " · 还没有优化稿"}
            </p>
          ) : (
            <p className="px-3.5 py-6 text-center text-[13px] text-muted-foreground">先上传一份原稿</p>
          )}

          <div className="border-b border-border px-3.5 py-3">
            <Button className="w-full" disabled={!active} onClick={() => setAskOpen(true)}>
              <Sparkles />
              去优化
            </Button>
          </div>

          <div className="flex items-center justify-between px-3.5 py-2.5">
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">
              已优化{loop.versions.length ? ` · ${loop.versions.length} 版` : ""}
            </span>
            {loop.versions.length > 1 && (
              <button
                type="button"
                onClick={() => setVersionsOpen((v) => !v)}
                className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground hover:text-foreground"
              >
                <ChevronDown size={12} className={cn(versionsOpen && "rotate-180")} />
                {versionsOpen ? "收起" : `还有 ${loop.versions.length - 1} 版`}
              </button>
            )}
          </div>

          {loop.versions.length === 0 && (
            <p className="px-3.5 pb-4 text-center text-[13px] text-muted-foreground">
              还没有优化稿，点上面去优化
            </p>
          )}

          {shownVersions.map((ver) => (
            <div
              key={ver.id}
              className={cn(
                "flex items-start gap-2 border-t border-border px-3.5 py-3",
                ver.is_current && "bg-primary/5",
              )}
            >
              <button type="button" onClick={() => setViewing(ver)} className="min-w-0 flex-1 text-left">
                <p className="font-mono text-[13px] font-semibold text-foreground">
                  v{ver.version}
                  {ver.is_current ? " · 当前" : ""}
                </p>
                <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                  {ver.note || MODEL_NAME[ver.model] || ver.model}
                  {` · ${ver.chars} 字`}
                  {ver.created_at ? ` · ${formatWhen(ver.created_at)}` : ""}
                </p>
              </button>
              <button
                type="button"
                onClick={() => setViewing(ver)}
                className="shrink-0 p-1 text-muted-foreground hover:text-foreground"
                aria-label="查看这一版"
              >
                <Eye size={14} />
              </button>
              <button
                type="button"
                onClick={() => void onDeleteVersion(ver.id)}
                className={cn(
                  "shrink-0 p-1",
                  confirmVersion === ver.id ? "text-destructive" : "text-muted-foreground hover:text-foreground",
                )}
                aria-label="删除这一版"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      <Dialog open={analyzeOpen} onOpenChange={setAnalyzeOpen}>
        <DialogContent>
          <div
            className="flex items-center justify-between border-b border-border px-4 pb-3"
            style={{ paddingTop: "calc(14px + env(safe-area-inset-top, 0px))" }}
          >
            <DialogTitle className="font-heading text-base font-semibold">去分析</DialogTitle>
            <Button variant="ghost" size="icon-sm" onClick={() => setAnalyzeOpen(false)} aria-label="关闭">
              <X size={16} />
            </Button>
          </div>
          <div className="flex flex-col gap-3 px-4 py-4">
            <textarea
              value={sopBrief}
              onChange={(e) => setSopBrief(e.target.value)}
              placeholder="你要怎么审这份简历，写需求就行"
              className="min-h-24 w-full resize-y border border-input bg-card/60 px-3 py-2 text-[13px] leading-relaxed text-foreground outline-none"
            />
            <div className="flex gap-1.5">
              {MODELS.map((m) => {
                const on = sopModels.includes(m.id);
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => toggleSopModel(m.id)}
                    className={cn(
                      "flex-1 border py-1.5 font-mono text-[11px] uppercase tracking-wide",
                      on ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground",
                    )}
                  >
                    {m.label}
                  </button>
                );
              })}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="outline"
                disabled={analyzing || generating || !sopBrief.trim()}
                onClick={() => void runDirect()}
              >
                <Search />
                {analyzing ? "在出报告" : "直接生成报告"}
              </Button>
              <Button disabled={generating || analyzing || !sopBrief.trim()} onClick={() => void generateSop()}>
                <Sparkles />
                {generating ? "在出图" : "先出流程图"}
              </Button>
            </div>
          </div>
          <div className="border-t border-border">
            <div className="flex items-center justify-between px-4 py-2.5">
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">
                SOP{mineSops.length ? ` · ${mineSops.length} 份` : ""}
              </span>
              {mineSops.length > 1 && (
                <button
                  type="button"
                  onClick={() => setSopsOpen((v) => !v)}
                  className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground hover:text-foreground"
                >
                  <ChevronDown size={12} className={cn(sopsOpen && "rotate-180")} />
                  {sopsOpen ? "收起" : `还有 ${mineSops.length - 1} 份`}
                </button>
              )}
            </div>
            {mineSops.length === 0 && (
              <p className="px-4 pb-4 text-center text-[13px] text-muted-foreground">写需求，出流程图</p>
            )}
            {(sopsOpen ? mineSops : mineSops.slice(0, 1)).map((row) => {
              const on = row.id === picked?.id;
              return (
                <div key={row.id} className={cn("border-t border-border", on && "bg-primary/5")}>
                  <div className="flex items-start gap-2 px-4 py-3">
                    <button
                      type="button"
                      onClick={() => setPickedSopId(row.id)}
                      className="min-w-0 flex-1 text-left"
                    >
                      <p className="truncate font-mono text-[13px] font-semibold text-foreground">{row.name}</p>
                      <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                        {row.steps.length} 步
                        {row.status === "used" ? " · 已出报告" : " · 未跑"}
                        {row.created_at ? ` · ${formatWhen(row.created_at)}` : ""}
                      </p>
                    </button>
                    <button
                      type="button"
                      onClick={() => void onDeleteSop(row.id)}
                      className={cn(
                        "shrink-0 p-1",
                        confirmSop === row.id ? "text-destructive" : "text-muted-foreground hover:text-foreground",
                      )}
                      aria-label="删除 SOP"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                  {on && row.steps.length > 0 && <SopFlow steps={row.steps} />}
                  {on && row.status !== "used" && row.steps.length > 0 && (
                    <div className="px-4 pb-3">
                      <Button className="w-full" disabled={!active || analyzing} onClick={() => void runAnalyze()}>
                        <Search />
                        {analyzing ? "在分析" : "按这张图分析"}
                      </Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={askOpen} onOpenChange={setAskOpen}>
        <DialogContent>
          <div
            className="flex items-center justify-between border-b border-border px-4 pb-3"
            style={{ paddingTop: "calc(14px + env(safe-area-inset-top, 0px))" }}
          >
            <DialogTitle className="font-heading text-base font-semibold">去优化</DialogTitle>
            <Button variant="ghost" size="icon-sm" onClick={() => setAskOpen(false)} aria-label="关闭">
              <X size={16} />
            </Button>
          </div>
          <div className="flex flex-col gap-3 px-4 py-4">
            <textarea
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              placeholder="你要怎么改这份简历，写需求就行"
              spellCheck={false}
              className="min-h-24 w-full resize-y border border-input bg-card/60 px-3 py-2 text-[13px] leading-relaxed text-foreground outline-none"
            />
            <div className="flex gap-1.5">
              {MODELS.map((m) => {
                const on = optModels.includes(m.id);
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => toggleOptModel(m.id)}
                    className={cn(
                      "flex-1 border py-1.5 font-mono text-[11px] uppercase tracking-wide",
                      on ? "border-primary bg-primary/10 text-primary font-semibold" : "border-border text-muted-foreground",
                    )}
                  >
                    {m.label}
                  </button>
                );
              })}
            </div>
            {loop.analyses.length === 0 ? (
              <p className="text-center text-[13px] text-muted-foreground">还没有报告，先去分析跑一份</p>
            ) : (
              <select
                value={reportId ?? ""}
                onChange={(e) => setReportId(e.target.value ? Number(e.target.value) : null)}
                className="w-full border border-border bg-background px-3 py-2 font-mono text-[12px] text-foreground"
              >
                {loop.analyses.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.title}
                  </option>
                ))}
              </select>
            )}
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="outline"
                disabled={!active || asking || generating || !brief.trim() || !reportId}
                onClick={() => void ask()}
              >
                <Search />
                {asking ? "在出建议" : "直接出建议"}
              </Button>
              <Button
                disabled={!active || generating || asking || !brief.trim() || !reportId}
                onClick={() => void generateOptSop()}
              >
                <Sparkles />
                {generating ? "在出图" : "先出流程图"}
              </Button>
            </div>
          </div>
          <div className="border-t border-border">
            <div className="flex items-center justify-between px-4 py-2.5">
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">
                SOP{optSops.length ? ` · ${optSops.length} 份` : ""}
              </span>
              {optSops.length > 1 && (
                <button
                  type="button"
                  onClick={() => setOptSopsOpen((v) => !v)}
                  className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground hover:text-foreground"
                >
                  <ChevronDown size={12} className={cn(optSopsOpen && "rotate-180")} />
                  {optSopsOpen ? "收起" : `还有 ${optSops.length - 1} 份`}
                </button>
              )}
            </div>
            {optSops.length === 0 && (
              <p className="px-4 pb-4 text-center text-[13px] text-muted-foreground">要多模型按图改，先出流程图</p>
            )}
            {(optSopsOpen ? optSops : optSops.slice(0, 1)).map((row) => {
              const on = row.id === pickedOpt?.id;
              return (
                <div key={row.id} className={cn("border-t border-border", on && "bg-primary/5")}>
                  <div className="flex items-start gap-2 px-4 py-3">
                    <button
                      type="button"
                      onClick={() => setPickedOptSopId(row.id)}
                      className="min-w-0 flex-1 text-left"
                    >
                      <p className="truncate font-mono text-[13px] font-semibold text-foreground">{row.name}</p>
                      <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                        {row.steps.length} 步
                        {row.status === "used" ? " · 已出建议" : " · 未跑"}
                        {row.created_at ? ` · ${formatWhen(row.created_at)}` : ""}
                      </p>
                    </button>
                    <button
                      type="button"
                      onClick={() => void onDeleteSop(row.id)}
                      className={cn(
                        "shrink-0 p-1",
                        confirmSop === row.id ? "text-destructive" : "text-muted-foreground hover:text-foreground",
                      )}
                      aria-label="删除 SOP"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                  {on && row.steps.length > 0 && <SopFlow steps={row.steps} />}
                  {on && row.status !== "used" && row.steps.length > 0 && (
                    <div className="px-4 pb-3">
                      <Button
                        className="w-full"
                        disabled={!active || asking}
                        onClick={() => void ask(row.id)}
                      >
                        <Search />
                        {asking ? "在出建议" : "按这张图出建议"}
                      </Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div className="border-t border-border">
            <div className="flex items-center justify-between px-4 py-2.5">
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">
                建议{loop.suggestions.length ? ` · ${loop.suggestions.length} 条` : ""}
              </span>
              {loop.suggestions.length > 0 && (
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">
                  待定 {pending.length} · 采纳 {adopted.length} · 不采纳 {rejected.length}
                </span>
              )}
            </div>
            {loop.suggestions.length === 0 && (
              <p className="px-4 pb-4 text-center text-[13px] text-muted-foreground">还没有建议</p>
            )}
            {loop.suggestions.map((item) => (
              <div key={item.id} className="border-t border-border px-4 py-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-mono text-[13px] font-semibold text-foreground">{item.title}</p>
                  <span className="shrink-0 font-mono text-[10px] uppercase tracking-wide text-muted-foreground-dim">
                    {MODEL_NAME[item.model] ?? item.model}
                    {` · ${STATUS_NAME[item.status]}`}
                  </span>
                </div>
                {item.quote ? (
                  <p className="mt-1 font-mono text-[11px] text-muted-foreground">「{item.quote}」</p>
                ) : null}
                <p className="mt-1 text-[13px] leading-relaxed text-foreground">{item.body}</p>
                <div className="mt-2 flex gap-2">
                  <Button
                    className="flex-1"
                    size="sm"
                    variant={item.status === "adopted" ? "default" : "outline"}
                    onClick={() => void onSetStatus(item.id, "adopted")}
                  >
                    <Check />
                    采纳
                  </Button>
                  <Button
                    className="flex-1"
                    size="sm"
                    variant={item.status === "rejected" ? "destructive" : "outline"}
                    onClick={() => void onSetStatus(item.id, "rejected")}
                  >
                    <X />
                    不采纳
                  </Button>
                </div>
              </div>
            ))}
            {adopted.length > 0 && (
              <div className="border-t border-border px-4 py-3">
                <Button className="w-full" disabled={applying} onClick={() => void applyAdopted()}>
                  {applying ? "在落" : `应用已采纳，落 v${(active?.current_version || 0) + 1}`}
                </Button>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
      <ResumeEditor
        open={!!editing}
        pane={pane}
        resume={editing ? { ...editing, title: draftTitle } : null}
        markdown={draftMd}
        finalMarkdown={draftFinal}
        saving={saving}
        onOpenChange={(open) => !open && setEditing(null)}
        onPane={setPane}
        onTitle={setDraftTitle}
        onMarkdown={setDraftMd}
        onSave={() => void onSave()}
      />
      <Dialog
        open={!!viewingReport}
        onOpenChange={(open) => {
          if (!open) setViewingReport(null);
        }}
      >
        <DialogContent>
          <div
            className="flex items-center justify-between border-b border-border px-4 pb-3"
            style={{ paddingTop: "calc(14px + env(safe-area-inset-top, 0px))" }}
          >
            <DialogTitle className="font-heading text-base font-semibold">分析报告</DialogTitle>
            <Button variant="ghost" size="icon-sm" onClick={() => setViewingReport(null)} aria-label="关闭">
              <X size={16} />
            </Button>
          </div>
          <div className="flex flex-col gap-3 px-4 py-4">
            <Input value={renameTitle} onChange={(e) => setRenameTitle(e.target.value)} placeholder="报告标题" />
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">
              {viewingReport?.sop_name || "SOP"}
              {viewingReport ? ` · ${viewingReport.finding_count || viewingReport.findings?.length || 0} 条` : ""}
              {viewingReport?.created_at ? ` · ${formatWhen(viewingReport.created_at)}` : ""}
            </p>
            <div className="max-h-[50vh] overflow-y-auto border border-border">
              {(viewingReport?.findings ?? []).map((item, i) => (
                <div key={`${item.title}-${i}`} className="border-b border-border px-3.5 py-3 last:border-b-0">
                  <p className="font-mono text-[13px] font-semibold text-foreground">{item.title}</p>
                  {item.quote ? (
                    <p className="mt-1 font-mono text-[11px] text-muted-foreground">「{item.quote}」</p>
                  ) : null}
                  <p className="mt-1 text-[13px] leading-relaxed text-foreground">{item.body}</p>
                </div>
              ))}
              {viewingReport && !(viewingReport.findings ?? []).length && (
                <p className="px-3.5 py-8 text-center text-[13px] text-muted-foreground">这份没有洞</p>
              )}
            </div>
            <Button className="w-full" disabled={renaming || !renameTitle.trim()} onClick={() => void onRenameReport()}>
              {renaming ? "保存中" : "保存标题"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog
        open={!!viewing}
        onOpenChange={(open) => {
          if (!open) {
            setViewing(null);
            setConfirmVersion(null);
          }
        }}
      >
        <DialogContent>
          <div
            className="flex items-center justify-between border-b border-border px-4 pb-3"
            style={{ paddingTop: "calc(14px + env(safe-area-inset-top, 0px))" }}
          >
            <DialogTitle className="font-heading text-base font-semibold">
              {viewing ? `v${viewing.version}${viewing.is_current ? " · 当前" : ""}` : "版本"}
            </DialogTitle>
            <Button variant="ghost" size="icon-sm" onClick={() => setViewing(null)} aria-label="关闭">
              <X size={16} />
            </Button>
          </div>
          <div className="flex flex-col gap-3 px-4 py-4">
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">
              {viewing?.note || "review"}
              {viewing ? ` · ${viewing.chars} 字` : ""}
            </p>
            <textarea
              value={viewing?.markdown ?? ""}
              readOnly
              spellCheck={false}
              className="min-h-[50vh] w-full resize-y border border-input bg-card/60 px-3.5 py-3 font-mono text-[13px] leading-relaxed text-muted-foreground outline-none"
            />
            {viewing && !viewing.is_current && (
              <Button
                className="w-full"
                onClick={() => {
                  void loop.activate(viewing.id).then(() => {
                    void reload();
                    setViewing({ ...viewing, is_current: true });
                    toast(`已切到 v${viewing.version}`, "success");
                  });
                }}
              >
                设为当前版本
              </Button>
            )}
            {viewing && (
              <Button
                className="w-full"
                variant={confirmVersion === viewing.id ? "destructive" : "outline"}
                onClick={() => void onDeleteVersion(viewing.id)}
              >
                <Trash2 />
                {confirmVersion === viewing.id ? "再点确认删除" : "删除这一版"}
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
