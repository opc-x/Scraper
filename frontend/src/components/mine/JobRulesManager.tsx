import * as React from "react";
import { Plus, Trash2, ChevronDown, Pencil, CircleHelp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { useJobRules, type JobRuleInput } from "@/hooks/useJobRules";
import type { JobRule } from "@/lib/types";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

const DIMENSIONS = [
  {
    id: "match",
    label: "匹配",
    groups: [
      { category: "match_cap", label: "硬顶" },
      { category: "match_config", label: "配置" },
      { category: "match_signal", label: "信号" },
      { category: "match_stack", label: "技术栈" },
      { category: "match_verdict", label: "分档" },
    ],
  },
  {
    id: "quality",
    label: "质量",
    groups: [
      { category: "quality_block", label: "拦截" },
      { category: "quality_suspect", label: "可疑" },
    ],
  },
  {
    id: "recall",
    label: "召回",
    groups: [{ category: "recall", label: "细则" }],
  },
  {
    id: "ingest",
    label: "入库",
    groups: [
      { category: "ingest_gate_config", label: "阈值" },
      { category: "ingest_gate", label: "条件" },
    ],
  },
] as const;

type DimensionId = (typeof DIMENSIONS)[number]["id"];

const CATEGORY_LABEL: Record<string, string> = Object.fromEntries(
  DIMENSIONS.flatMap((d) => d.groups.map((g) => [g.category, `${d.label} · ${g.label}`])),
);

const emptyForm = (category = "match_stack"): JobRuleInput => ({
  category,
  key: "",
  label: "",
  pattern: "",
  weight: 0,
  severity: "",
  enabled: true,
  rationale: "",
  config: {},
  sort_order: 0,
});

function errMsg(e: unknown): string {
  if (!(e instanceof ApiError)) return "操作失败";
  try {
    const j = JSON.parse(e.message) as { detail?: string };
    if (typeof j.detail === "string") return j.detail;
  } catch {
    /* raw */
  }
  return e.message || "操作失败";
}

function RuleEditor({
  open,
  title,
  initial,
  categories,
  lockIdentity,
  onClose,
  onSubmit,
}: {
  open: boolean;
  title: string;
  initial: JobRuleInput;
  categories: string[];
  lockIdentity?: boolean;
  onClose: () => void;
  onSubmit: (body: JobRuleInput) => Promise<void>;
}) {
  const [form, setForm] = React.useState(initial);
  const [configText, setConfigText] = React.useState(JSON.stringify(initial.config || {}, null, 0));
  const [saving, setSaving] = React.useState(false);
  const toast = useToast();

  React.useEffect(() => {
    if (!open) return;
    setForm(initial);
    setConfigText(JSON.stringify(initial.config || {}, null, 0));
  }, [open, initial]);

  const set = <K extends keyof JobRuleInput>(key: K, value: JobRuleInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const codeDriven = form.category === "ingest_gate" && form.key !== "java";

  const save = async () => {
    let config: Record<string, unknown> = {};
    try {
      config = configText.trim() ? (JSON.parse(configText) as Record<string, unknown>) : {};
    } catch {
      toast("config 必须是合法 JSON", "error");
      return;
    }
    if (!form.key.trim()) {
      toast("key 不能为空", "error");
      return;
    }
    setSaving(true);
    try {
      await onSubmit({ ...form, config, key: form.key.trim(), label: form.label.trim() || form.key.trim() });
      onClose();
    } catch (e) {
      toast(errMsg(e), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogTitle>{title}</DialogTitle>
        <div className="flex flex-col gap-2.5 pt-1">
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">category</span>
            <select
              value={form.category}
              disabled={lockIdentity}
              onChange={(e) => set("category", e.target.value)}
              className="border border-input bg-card px-2 py-2 font-mono text-sm disabled:opacity-60"
            >
              {(categories.length ? categories : Object.keys(CATEGORY_LABEL)).map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_LABEL[c] || c}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">key</span>
            <Input
              value={form.key}
              disabled={lockIdentity}
              onChange={(e) => set("key", e.target.value)}
              placeholder="java"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">label</span>
            <Input value={form.label} onChange={(e) => set("label", e.target.value)} placeholder="展示名" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">pattern</span>
            {codeDriven ? (
              <p className="border border-dashed border-border bg-card/60 px-2 py-2 text-[12px] text-muted-foreground">
                这条由代码逻辑判断（`app/core/job_derive.py` 里的 `_is_wfh` 等函数），不是正则匹配，这里没有可编辑的东西。
              </p>
            ) : (
              <textarea
                value={form.pattern}
                onChange={(e) => set("pattern", e.target.value)}
                placeholder="正则，配置类可空"
                className="min-h-20 w-full resize-y border border-input bg-card px-2 py-2 font-mono text-[12px]"
              />
            )}
          </label>
          <div className="grid grid-cols-3 gap-2">
            <label className="flex flex-col gap-1">
              <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">weight</span>
              <Input
                type="number"
                value={form.weight}
                onChange={(e) => set("weight", Number(e.target.value) || 0)}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">severity</span>
              <select
                value={form.severity}
                onChange={(e) => set("severity", e.target.value)}
                className="border border-input bg-card px-2 py-2 font-mono text-sm"
              >
                <option value="">（无）</option>
                <option value="block">block</option>
                <option value="suspect">suspect</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">sort</span>
              <Input
                type="number"
                value={form.sort_order}
                onChange={(e) => set("sort_order", Number(e.target.value) || 0)}
              />
            </label>
          </div>
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">rationale</span>
            <Input value={form.rationale} onChange={(e) => set("rationale", e.target.value)} placeholder="为什么有这条" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">config JSON</span>
            <textarea
              value={configText}
              onChange={(e) => setConfigText(e.target.value)}
              className="min-h-16 w-full resize-y border border-input bg-card px-2 py-2 font-mono text-[12px]"
            />
          </label>
          <label className="flex items-center gap-2 font-mono text-[12px]">
            <input type="checkbox" checked={form.enabled} onChange={(e) => set("enabled", e.target.checked)} />
            enabled
          </label>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" onClick={onClose} disabled={saving}>
              取消
            </Button>
            <Button onClick={save} disabled={saving}>
              {saving ? "保存中…" : "保存"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RuleRow({
  rule,
  onEdit,
  onToggle,
  onDelete,
}: {
  rule: JobRule;
  onEdit: () => void;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className={cn("border border-border bg-card p-3", !rule.enabled && "opacity-55")}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex flex-wrap items-center gap-1.5">
          <span className="truncate font-mono text-sm font-bold">{rule.label || rule.key}</span>
          <span className="font-mono text-[10px] text-muted-foreground">w{rule.weight}</span>
          {rule.severity ? (
            <Badge variant={rule.severity === "block" ? "destructive" : "secondary"} className="text-[10px]">
              {rule.severity}
            </Badge>
          ) : null}
          {!rule.enabled && (
            <Badge variant="outline" className="text-[10px] text-muted-foreground">
              停用
            </Badge>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button type="button" onClick={onEdit} className="p-1 text-muted-foreground hover:text-foreground" aria-label="编辑">
            <Pencil size={13} />
          </button>
          <button
            type="button"
            onClick={onToggle}
            className="px-1 font-mono text-[10px] text-muted-foreground hover:text-foreground"
          >
            {rule.enabled ? "停用" : "启用"}
          </button>
          <button type="button" onClick={onDelete} className="p-1 text-muted-foreground hover:text-destructive" aria-label="删除">
            <Trash2 size={13} />
          </button>
        </div>
      </div>
      <button type="button" onClick={() => setOpen((v) => !v)} className="mt-1 flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
        {open ? "收起" : "细则"}
        <ChevronDown size={12} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-2 space-y-1 border-t border-border pt-2 text-[11px] text-muted-foreground">
          <p className="font-mono text-[10px]">{rule.key}</p>
          {rule.rationale && <p>{rule.rationale}</p>}
          {rule.category === "ingest_gate" && rule.key !== "java" ? (
            <p className="text-muted-foreground-dim">由代码逻辑判断，不是正则——这里没有可看的匹配规则。</p>
          ) : (
            rule.pattern && <p className="break-all font-mono text-[10px] text-muted-foreground-dim">{rule.pattern}</p>
          )}
          {Object.keys(rule.config || {}).length > 0 && (
            <p className="break-all font-mono text-[10px] text-muted-foreground-dim">{JSON.stringify(rule.config)}</p>
          )}
        </div>
      )}
    </div>
  );
}

function HelpHint() {
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    const onDoc = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={wrapRef} className="group relative">
      <button
        type="button"
        aria-label="系统规则说明"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex size-8 items-center justify-center text-muted-foreground hover:text-foreground"
      >
        <CircleHelp size={15} />
      </button>
      <div
        role="tooltip"
        className={cn(
          "absolute right-0 top-full z-30 mt-1 w-[min(19.5rem,calc(100vw-2.5rem))] border border-border-strong bg-popover p-3 text-[12px] leading-relaxed text-popover-foreground",
          open ? "block" : "hidden [@media(hover:hover)_and_(pointer:fine)]:group-hover:block",
        )}
      >
        <p>
          <span className="font-mono text-[10px] uppercase tracking-wide text-primary">干什么</span>
          {" 改打分口径、垃圾拦截、召回条件。不是首页拉渠道，也不是给单个职位打标签。"}
        </p>
        <p className="mt-2">
          <span className="font-mono text-[10px] uppercase tracking-wide text-primary">何时改</span>
          {" 口径变了才动，比如不要某技术栈、封顶分要调。平时别碰。"}
        </p>
        <p className="mt-2">
          <span className="font-mono text-[10px] uppercase tracking-wide text-primary">怎么用</span>
          {" 先选匹配/质量/召回/入库，再选分组看细则。点「细则」看正则和权重；停用=这条不算。改完立刻作用到之后的打分。"}
        </p>
        <p className="mt-2">
          <span className="font-mono text-[10px] uppercase tracking-wide text-primary">入库是什么</span>
          {" 落库前的软过滤门槛，跟上面几档打分口径不是一回事：「阈值」那条的权重就是百分比（0-100），停用=总开关关闭；「条件」下每条的权重是它在几项里的占比（Java 是硬性必过项，不算在占比里）。未达标的职位照样落库，只是默认从列表隐藏。「java」这条的 pattern 是真生效的正则——改它就能把方向换成 nodejs/python；其余几条没有正则可编辑，是代码里写死的判断函数，权重/启停照样有效，只是没有 pattern 可看。"}
        </p>
        <p className="mt-2">
          <span className="font-mono text-[10px] uppercase tracking-wide text-primary">AI 复议</span>
          {" 「规则权重」「AI 权重」两条控制 scripts/rescue_ingest_gate.py 这个批量脚本——它只捞回 Java 已命中、但其余条件比例不够被拦掉的职位，跑本机 AI 给个二次判断，跟规则分混合后再看是否达标，需要手动跑脚本，不是自动的。"}
        </p>
      </div>
    </div>
  );
}

export function JobRulesManager() {
  const { rules, categories, loading, create, update, remove } = useJobRules();
  const toast = useToast();
  const [dimensionId, setDimensionId] = React.useState<DimensionId>("match");
  const [activeCat, setActiveCat] = React.useState("match_cap");
  const [editor, setEditor] = React.useState<{ mode: "create" | "edit"; initial: JobRuleInput; id?: number } | null>(null);

  const byCat = React.useMemo(() => {
    const map = new Map<string, JobRule[]>();
    for (const r of rules) {
      const list = map.get(r.category) ?? [];
      list.push(r);
      map.set(r.category, list);
    }
    return map;
  }, [rules]);

  const dimension = DIMENSIONS.find((d) => d.id === dimensionId) ?? DIMENSIONS[0];
  const visibleGroups = dimension.groups.filter((g) => (byCat.get(g.category) ?? []).length > 0);
  const activeGroup = visibleGroups.find((g) => g.category === activeCat) ?? visibleGroups[0];
  const activeList = activeGroup ? (byCat.get(activeGroup.category) ?? []) : [];

  const switchDimension = (id: DimensionId) => {
    setDimensionId(id);
    const next = DIMENSIONS.find((d) => d.id === id);
    const first = next?.groups.find((g) => (byCat.get(g.category) ?? []).length)?.category;
    if (first) setActiveCat(first);
  };

  const openCreate = () =>
    setEditor({ mode: "create", initial: emptyForm(activeGroup?.category || "match_stack") });
  const openEdit = (r: JobRule) =>
    setEditor({
      mode: "edit",
      id: r.id,
      initial: {
        category: r.category,
        key: r.key,
        label: r.label,
        pattern: r.pattern,
        weight: r.weight,
        severity: r.severity || "",
        enabled: r.enabled,
        rationale: r.rationale,
        config: r.config || {},
        sort_order: r.sort_order,
      },
    });

  return (
    <section className="flex flex-col gap-3 border border-border bg-card/40 p-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">系统规则</h3>
          <p className="mt-0.5 text-[12px] text-muted-foreground">打分 / 质量 / 召回口径，低频改。</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <HelpHint />
          <Button size="sm" className="gap-1" onClick={openCreate}>
            <Plus size={14} />
            新建
          </Button>
        </div>
      </div>

      {!loading && (
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 [scrollbar-width:none]">
          {DIMENSIONS.map((d) => (
            <button
              key={d.id}
              type="button"
              onClick={() => switchDimension(d.id)}
              className={cn(
                "shrink-0 border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide transition-colors",
                d.id === dimensionId
                  ? "border-primary bg-primary text-primary-foreground font-semibold"
                  : "border-border-strong text-muted-foreground hover:text-foreground",
              )}
            >
              {d.label}
            </button>
          ))}
        </div>
      )}

      {!loading && visibleGroups.length > 1 && (
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 [scrollbar-width:none]">
          {visibleGroups.map((g) => (
            <button
              key={g.category}
              type="button"
              onClick={() => setActiveCat(g.category)}
              className={cn(
                "shrink-0 border px-2.5 py-1 font-mono text-[10px] tracking-wide transition-colors",
                g.category === activeGroup?.category
                  ? "border-foreground bg-foreground text-background font-semibold"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {g.label}
              <span className="ml-1 opacity-60">{(byCat.get(g.category) ?? []).length}</span>
            </button>
          ))}
        </div>
      )}

      {loading && <p className="text-sm text-muted-foreground">加载中…</p>}
      {!loading && rules.length === 0 && <p className="text-sm text-muted-foreground">还没有规则</p>}
      {!loading && rules.length > 0 && visibleGroups.length === 0 && (
        <p className="text-sm text-muted-foreground">这个维度还没有细则</p>
      )}

      <div className="flex flex-col gap-2">
        {activeList.map((r) => (
          <RuleRow
            key={r.id}
            rule={r}
            onEdit={() => openEdit(r)}
            onToggle={async () => {
              try {
                await update(r.id, { enabled: !r.enabled });
                toast(r.enabled ? "已停用" : "已启用", "success");
              } catch (e) {
                toast(errMsg(e), "error");
              }
            }}
            onDelete={async () => {
              if (!confirm(`删除规则 ${r.category}/${r.key}？`)) return;
              try {
                await remove(r.id);
                toast("已删除", "success");
              } catch (e) {
                toast(errMsg(e), "error");
              }
            }}
          />
        ))}
      </div>

      {editor && (
        <RuleEditor
          open
          title={editor.mode === "create" ? "新建规则" : "编辑规则"}
          initial={editor.initial}
          categories={categories}
          lockIdentity={editor.mode === "edit"}
          onClose={() => setEditor(null)}
          onSubmit={async (body) => {
            if (editor.mode === "create") {
              await create(body);
              toast("已创建", "success");
              const dim = DIMENSIONS.find((d) => d.groups.some((g) => g.category === body.category));
              if (dim) setDimensionId(dim.id);
              setActiveCat(body.category);
            } else if (editor.id != null) {
              await update(editor.id, {
                label: body.label,
                pattern: body.pattern,
                weight: body.weight,
                severity: body.severity,
                enabled: body.enabled,
                rationale: body.rationale,
                config: body.config,
                sort_order: body.sort_order,
              });
              toast("已保存", "success");
            }
          }}
        />
      )}
    </section>
  );
}
