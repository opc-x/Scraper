import * as React from "react";
import { Plus, Check, Trash2, X, ChevronDown, ChevronLeft, ChevronRight, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { useValueTags } from "@/hooks/useValueTags";
import type { ValueTag } from "@/lib/types";
import { tagSeverity, SEVERITY_LABEL, SEVERITY_BADGE_VARIANT } from "@/lib/valueTagSeverity";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 5;
const NEW_CATEGORY = "__new__";

const POLARITY_OPTIONS = [
  { value: 1 as const, label: "正面", hint: "加分", dot: "bg-primary", active: "border-primary bg-primary/10 text-primary" },
  { value: 0 as const, label: "中性", hint: "不计分", dot: "bg-warning", active: "border-warning bg-warning/10 text-warning" },
  { value: -1 as const, label: "负面", hint: "减分", dot: "bg-destructive", active: "border-destructive bg-destructive/10 text-destructive" },
];

function PolarityPicker({ value, onChange }: { value: -1 | 0 | 1; onChange: (value: -1 | 0 | 1) => void }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {POLARITY_OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={cn(
            "flex min-w-0 items-center justify-center gap-2 border border-border-strong px-2 py-2 font-mono text-xs text-muted-foreground",
            value === option.value && option.active,
          )}
        >
          <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", option.dot)} />
          <span>{option.label}</span>
          <span className="hidden text-[10px] opacity-70 sm:inline">· {option.hint}</span>
        </button>
      ))}
    </div>
  );
}

function TagRow({
  tag,
  onApprove,
  onUnapprove,
  onDelete,
  onSaveEdit,
}: {
  tag: ValueTag;
  onApprove: () => void;
  onUnapprove: () => void;
  onDelete: () => void;
  onSaveEdit: (fields: Pick<ValueTag, "label" | "pattern" | "polarity" | "weight">) => Promise<unknown>;
}) {
  const [editing, setEditing] = React.useState(false);
  const [expanded, setExpanded] = React.useState(false);
  const [label, setLabel] = React.useState(tag.label);
  const [pattern, setPattern] = React.useState(tag.pattern);
  const [polarity, setPolarity] = React.useState(tag.polarity);
  const [weight, setWeight] = React.useState(tag.weight);
  const [saving, setSaving] = React.useState(false);

  const severity = tagSeverity(tag.polarity);

  const save = async () => {
    setSaving(true);
    try {
      await onSaveEdit({ label, pattern, polarity, weight });
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-border bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Badge variant={SEVERITY_BADGE_VARIANT[severity]} className="shrink-0">
            {SEVERITY_LABEL[severity]}
          </Badge>
          <span className="truncate font-mono text-sm font-bold">{tag.label}</span>
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground">权重 {tag.weight}</span>
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground-dim">· {tag.category}</span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {tag.status === "draft" ? (
            <>
              <button type="button" onClick={onApprove} className="p-1 text-primary hover:opacity-80" aria-label="确认启用">
                <Check size={15} />
              </button>
              <button type="button" onClick={onDelete} className="p-1 text-destructive hover:opacity-80" aria-label="丢弃">
                <X size={15} />
              </button>
            </>
          ) : (
            <>
              <button type="button" onClick={() => setEditing((v) => !v)} className="font-mono text-[10px] text-muted-foreground hover:text-foreground">
                编辑
              </button>
              <button type="button" onClick={onUnapprove} className="ml-2 font-mono text-[10px] text-muted-foreground hover:text-foreground">
                停用
              </button>
              <button type="button" onClick={onDelete} className="ml-2 p-1 text-muted-foreground hover:text-destructive" aria-label="删除">
                <Trash2 size={13} />
              </button>
            </>
          )}
        </div>
      </div>

      {!editing ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1.5 flex w-full items-start justify-between gap-2 text-left"
        >
          <p className={cn("min-w-0 flex-1 text-xs text-muted-foreground", !expanded && "truncate")}>
            {tag.rationale || tag.pattern}
          </p>
          <ChevronDown size={13} className={cn("mt-0.5 shrink-0 text-muted-foreground-dim transition-transform", expanded && "rotate-180")} />
        </button>
      ) : null}
      {!editing && expanded && (
        <p className="mt-1 break-all font-mono text-[10px] text-muted-foreground-dim">{tag.pattern}</p>
      )}

      {editing && (
        <div className="mt-2 flex flex-col gap-2">
          <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="标签名" className="h-8 text-sm" />
          <Input value={pattern} onChange={(e) => setPattern(e.target.value)} placeholder="正则" className="h-8 font-mono text-xs" />
          <div className="flex items-center gap-2">
            <div className="flex-1">
              <PolarityPicker value={polarity} onChange={setPolarity} />
            </div>
            <Input
              type="number"
              min={5}
              max={30}
              value={weight}
              onChange={(e) => setWeight(Number(e.target.value))}
              className="h-8 w-20 text-sm"
            />
            <Button size="sm" disabled={saving} onClick={save}>
              保存
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

type TagActions = {
  onApprove: (id: number) => void;
  onUnapprove: (id: number) => void;
  onDelete: (id: number) => void;
  onSaveEdit: (id: number, fields: Pick<ValueTag, "label" | "pattern" | "polarity" | "weight">) => Promise<unknown>;
};

function CategoryGroup({ category, tags, actions }: { category: string; tags: ValueTag[]; actions: TagActions }) {
  const [page, setPage] = React.useState(0);
  const totalPages = Math.max(1, Math.ceil(tags.length / PAGE_SIZE));
  const pageSafe = Math.min(page, totalPages - 1);
  const pageTags = tags.slice(pageSafe * PAGE_SIZE, pageSafe * PAGE_SIZE + PAGE_SIZE);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <p className="font-mono text-[10px] uppercase tracking-wide text-primary">{category}</p>
        <span className="font-mono text-[10px] text-muted-foreground">{tags.length} 条</span>
      </div>
      {pageTags.map((t) => (
        <TagRow
          key={t.id}
          tag={t}
          onApprove={() => actions.onApprove(t.id)}
          onUnapprove={() => actions.onUnapprove(t.id)}
          onDelete={() => actions.onDelete(t.id)}
          onSaveEdit={(fields) => actions.onSaveEdit(t.id, fields)}
        />
      ))}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-1">
          <button
            type="button"
            disabled={pageSafe <= 0}
            onClick={() => setPage(pageSafe - 1)}
            className="p-1 text-muted-foreground disabled:opacity-30"
            aria-label="上一页"
          >
            <ChevronLeft size={15} />
          </button>
          <span className="font-mono text-[10px] text-muted-foreground">
            {pageSafe + 1} / {totalPages}
          </span>
          <button
            type="button"
            disabled={pageSafe >= totalPages - 1}
            onClick={() => setPage(pageSafe + 1)}
            className="p-1 text-muted-foreground disabled:opacity-30"
            aria-label="下一页"
          >
            <ChevronRight size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

function NewTagDialog({
  open,
  onOpenChange,
  knownCategories,
  onDraft,
  onApprove,
  onDelete,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  knownCategories: string[];
  onDraft: (description: string, category: string, polarity: -1 | 0 | 1) => Promise<ValueTag>;
  onApprove: (id: number) => void;
  onDelete: (id: number) => void;
}) {
  const [category, setCategory] = React.useState(knownCategories[0] ?? "价值观");
  const [newCategory, setNewCategory] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [polarity, setPolarity] = React.useState<-1 | 0 | 1>(0);
  const [drafting, setDrafting] = React.useState(false);
  const [pending, setPending] = React.useState<ValueTag | null>(null);
  const toast = useToast();

  const pickingNewCategory = category === NEW_CATEGORY;
  const finalCategory = pickingNewCategory ? newCategory.trim() : category;
  const canSubmit = description.trim() && finalCategory && !drafting;

  const reset = () => {
    setDescription("");
    setNewCategory("");
    setPolarity(0);
    setPending(null);
  };

  const submit = async () => {
    if (!canSubmit) return;
    setDrafting(true);
    try {
      const tag = await onDraft(description.trim(), finalCategory, polarity);
      setPending(tag);
    } catch (err) {
      toast(err instanceof Error ? err.message : "生成失败，换个说法再试", "error");
    } finally {
      setDrafting(false);
    }
  };

  const confirmPending = () => {
    if (!pending) return;
    onApprove(pending.id);
    toast("已启用");
    reset();
    onOpenChange(false);
  };

  const discardPending = () => {
    if (!pending) return;
    onDelete(pending.id);
    reset();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) reset();
      }}
    >
      <DialogContent className="p-4">
        <DialogTitle className="mb-4 font-heading text-lg font-semibold">新增标签</DialogTitle>

        {!pending ? (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">标签颜色</label>
              <PolarityPicker value={polarity} onChange={setPolarity} />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">维度</label>
              <div className="flex gap-2">
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="h-10 flex-1 border border-border-strong bg-card px-2 font-mono text-xs text-foreground"
                >
                  {knownCategories.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                  <option value={NEW_CATEGORY}>+ 新建维度…</option>
                </select>
              </div>
              {pickingNewCategory && (
                <Input
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                  placeholder="新维度名，比如「稳定性」"
                />
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">描述信号</label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="用大白话描述，比如「强制打卡算减分」"
              />
            </div>

            <Button disabled={!canSubmit} onClick={submit} className="mt-1 w-full gap-1.5">
              {drafting ? "生成中…" : (
                <>
                  <Sparkles size={14} /> AI 生成
                </>
              )}
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <TagRow
              tag={pending}
              onApprove={confirmPending}
              onUnapprove={() => {}}
              onDelete={discardPending}
              onSaveEdit={async (fields) => setPending({ ...pending, ...fields })}
            />
            <div className="flex gap-2">
              <Button className="flex-1" onClick={confirmPending}>
                确认启用
              </Button>
              <Button variant="outline" className="flex-1" onClick={discardPending}>
                丢弃重来
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function ValueTagManager() {
  const { tags, loading, draft, update, approve, unapprove, remove } = useValueTags();
  const [dialogOpen, setDialogOpen] = React.useState(false);

  const drafts = tags.filter((t) => t.status === "draft");
  const approved = tags.filter((t) => t.status === "approved");
  const categories = React.useMemo(() => {
    const groups = new Map<string, ValueTag[]>();
    for (const t of approved) {
      const list = groups.get(t.category) ?? [];
      list.push(t);
      groups.set(t.category, list);
    }
    return [...groups.entries()];
  }, [approved]);

  const knownCategories = React.useMemo(() => {
    const set = new Set(tags.map((t) => t.category));
    set.add("价值观");
    return [...set];
  }, [tags]);

  const [activeCategory, setActiveCategory] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (categories.length === 0) return;
    if (!activeCategory || !categories.some(([c]) => c === activeCategory)) {
      setActiveCategory(categories[0][0]);
    }
  }, [categories, activeCategory]);
  const activeGroup = categories.find(([c]) => c === activeCategory);

  const actions: TagActions = {
    onApprove: (id) => approve(id),
    onUnapprove: (id) => unapprove(id),
    onDelete: (id) => remove(id),
    onSaveEdit: (id, fields) => update(id, fields),
  };

  return (
    <div className="flex flex-col gap-3 border border-border bg-card p-3.5">
      <div className="flex items-center justify-between">
        <h3 className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">标签管理</h3>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] text-muted-foreground">{approved.length} 条生效</span>
          <Button size="sm" onClick={() => setDialogOpen(true)} className="gap-1">
            <Plus size={13} /> 新增
          </Button>
        </div>
      </div>

      {!loading && drafts.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="font-mono text-[10px] uppercase tracking-wide text-warning">待确认</p>
          {drafts.map((t) => (
            <TagRow
              key={t.id}
              tag={t}
              onApprove={() => actions.onApprove(t.id)}
              onUnapprove={() => actions.onUnapprove(t.id)}
              onDelete={() => actions.onDelete(t.id)}
              onSaveEdit={(fields) => actions.onSaveEdit(t.id, fields)}
            />
          ))}
        </div>
      )}

      {!loading && categories.length > 1 && (
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 [scrollbar-width:none]">
          {categories.map(([category]) => (
            <button
              key={category}
              type="button"
              onClick={() => setActiveCategory(category)}
              className={cn(
                "shrink-0 border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide transition-colors",
                category === activeCategory
                  ? "border-primary bg-primary text-primary-foreground font-semibold"
                  : "border-border-strong text-muted-foreground hover:text-foreground",
              )}
            >
              {category}
            </button>
          ))}
        </div>
      )}

      {!loading && activeGroup && (
        <CategoryGroup category={activeGroup[0]} tags={activeGroup[1]} actions={actions} />
      )}

      <NewTagDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        knownCategories={knownCategories}
        onDraft={draft}
        onApprove={(id) => actions.onApprove(id)}
        onDelete={(id) => actions.onDelete(id)}
      />
    </div>
  );
}
