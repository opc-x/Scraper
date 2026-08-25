import * as React from "react";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api";
import type { ChannelSchemaEntry } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { TelegramAccountManager } from "@/components/telegram/TelegramAccountManager";

interface ChannelConfigFormProps {
  channelId: string;
  schema: ChannelSchemaEntry;
  syncSupported: boolean;
  onSaved: () => void;
}

interface SyncLog {
  at: string;
  message: string;
}

interface SyncRun {
  id: number;
  channel: string;
  status: "queued" | "running" | "succeeded" | "failed";
  pulled: number;
  coverage: string;
  error: string;
  logs: SyncLog[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

interface SyncPreset {
  id: number;
  channel: string;
  name: string;
  query: string;
  created_at: string;
  updated_at: string;
}

const FAILURE_ACTION: Record<string, string> = {
  boss: "重新登录 zhipin.com，复制最新 Cookie 保存；如果弹出安全验证，先在浏览器中完成验证，再重新拉取。",
  telegram: "检查 Telegram 账号是否在线、监听来源是否可访问、DeepSeek Key 是否有效，然后重试。",
  discord: "检查 User Token 是否过期、账号是否有频道权限、监听来源 ID 是否正确，然后重试。",
  x: "重新确认 X 浏览器登录状态和 DeepSeek Key，然后重试。",
  v2ex: "确认网络能访问 V2EX Feed，然后重试。",
  eleduck: "确认网络能访问电鸭公开 API，然后重试。",
};

export function ChannelConfigForm({ channelId, schema, syncSupported, onSaved }: ChannelConfigFormProps) {
  const [values, setValues] = React.useState<Record<string, string>>({});
  const [enabled, setEnabled] = React.useState(false);
  const [syncQuery, setSyncQuery] = React.useState("");
  const [presets, setPresets] = React.useState<SyncPreset[]>([]);
  const [presetName, setPresetName] = React.useState("");
  const [editingPresetId, setEditingPresetId] = React.useState<number | null>(null);
  const [presetSaving, setPresetSaving] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [syncing, setSyncing] = React.useState(false);
  const [syncRun, setSyncRun] = React.useState<SyncRun | null>(null);
  const toast = useToast();

  React.useEffect(() => {
    setLoading(true);
    apiGet<{ channels: Record<string, Record<string, unknown>> }>("/api/channels/config")
      .then((res) => {
        const cfg = res.channels[channelId] ?? {};
        setEnabled(Boolean(cfg.enabled));
        setSyncQuery(String(cfg.sync_query ?? ""));
        const next: Record<string, string> = {};
        for (const f of schema.fields) next[f.key] = String(cfg[f.key] ?? "");
        setValues(next);
      })
      .finally(() => setLoading(false));
  }, [channelId, schema.fields]);

  const loadPresets = React.useCallback(() => {
    if (!syncSupported) return Promise.resolve();
    return apiGet<{ presets: SyncPreset[] }>(`/api/channels/${channelId}/sync-presets`)
      .then((result) => setPresets(result.presets));
  }, [channelId, syncSupported]);

  React.useEffect(() => {
    void loadPresets();
  }, [loadPresets]);

  const loadSyncRun = React.useCallback(async () => {
    const result = await apiGet<{ run: SyncRun | null }>(`/api/channels/${channelId}/sync/latest`);
    setSyncRun(result.run);
    setSyncing(result.run?.status === "queued" || result.run?.status === "running");
    return result.run;
  }, [channelId]);

  React.useEffect(() => {
    if (!syncSupported) return;
    void loadSyncRun();
  }, [loadSyncRun, syncSupported]);

  React.useEffect(() => {
    if (!syncing) return;
    const timer = window.setInterval(() => {
      void loadSyncRun().then((run) => {
        if (run?.status === "succeeded" || run?.status === "failed") {
          window.dispatchEvent(new Event("scraped-updated"));
        }
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [loadSyncRun, syncing]);

  const save = async () => {
    setSaving(true);
    try {
      await apiPut("/api/channels/config", { channel: channelId, enabled, sync_query: syncQuery, ...values });
      toast("已保存");
      onSaved();
    } catch {
      toast("保存失败", "error");
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setSaving(true);
    try {
      await apiDelete(`/api/channels/config/${channelId}`);
      toast("已重置");
      setEnabled(false);
      setSyncQuery("");
      const next: Record<string, string> = {};
      for (const f of schema.fields) next[f.key] = "";
      setValues(next);
      onSaved();
    } catch {
      toast("重置失败", "error");
    } finally {
      setSaving(false);
    }
  };

  const syncRecent = async () => {
    setSyncing(true);
    try {
      await apiPut("/api/channels/config", {
        channel: channelId,
        enabled,
        sync_query: syncQuery,
        ...values,
      });
      onSaved();
      const result = await apiPost<{ run: SyncRun; already_running: boolean }>(`/api/channels/${channelId}/sync`, { query: syncQuery });
      setSyncRun(result.run);
      toast(result.already_running ? "已有拉取任务正在运行" : "拉取任务已启动");
    } catch (error) {
      const message = error instanceof Error ? error.message : "拉取失败";
      setSyncing(false);
      toast(message, "error");
    }
  };

  const savePreset = async () => {
    if (!presetName.trim() || !syncQuery.trim()) {
      toast("先填写预设名称和抓取查询", "error");
      return;
    }
    setPresetSaving(true);
    try {
      const body = { name: presetName, query: syncQuery };
      if (editingPresetId) {
        await apiPut(`/api/channels/${channelId}/sync-presets/${editingPresetId}`, body);
        toast("查询预设已更新");
      } else {
        await apiPost(`/api/channels/${channelId}/sync-presets`, body);
        toast("查询预设已新增");
      }
      setPresetName("");
      setEditingPresetId(null);
      await loadPresets();
    } catch (error) {
      toast(error instanceof Error ? error.message : "保存预设失败", "error");
    } finally {
      setPresetSaving(false);
    }
  };

  const deletePreset = async (preset: SyncPreset) => {
    if (!window.confirm(`删除查询预设「${preset.name}」？`)) return;
    try {
      await apiDelete(`/api/channels/${channelId}/sync-presets/${preset.id}`);
      if (editingPresetId === preset.id) {
        setEditingPresetId(null);
        setPresetName("");
      }
      await loadPresets();
      toast("查询预设已删除");
    } catch (error) {
      toast(error instanceof Error ? error.message : "删除预设失败", "error");
    }
  };

  if (loading) return <p className="text-sm text-muted-foreground">加载中…</p>;

  return (
    <div className="flex flex-col gap-4">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="size-4 accent-[var(--primary)]"
        />
        启用此渠道
      </label>

      {schema.fields.map((f) => (
        <div key={f.key} className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-muted-foreground">
            {f.label}
            {f.required && <span className="text-destructive"> *</span>}
          </label>
          {f.type === "textarea" ? (
            <textarea
              value={values[f.key] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
              placeholder={f.placeholder}
              rows={4}
              className="rounded-[var(--radius-md)] border border-input bg-card/60 px-3.5 py-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          ) : (
            <Input
              type={f.type === "password" ? "password" : "text"}
              value={values[f.key] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
              placeholder={f.placeholder}
            />
          )}
          {f.help && <p className="text-[11px] text-muted-foreground">{f.help}</p>}
        </div>
      ))}

      {channelId === "telegram" && <TelegramAccountManager />}

      <div className="flex gap-2 pt-1">
        <Button onClick={save} disabled={saving} className="flex-1">
          {saving ? "保存中…" : "保存"}
        </Button>
        <Button variant="outline" onClick={reset} disabled={saving}>
          重置
        </Button>
      </div>

      {syncSupported && (
        <div className="border-t border-border pt-4">
          <div className="mb-4">
            <div className="mb-1.5 flex items-center justify-between">
              <label className="text-xs font-medium">抓取查询</label>
              <span
                title={'语法：关键字 | 地点 | 天数\n列之间是“且”，列内可写 or / and。\n例：java or nodejs | remote or 远程 or 杭州 | 90'}
                className="flex size-5 cursor-help items-center justify-center rounded-full border border-border font-mono text-[11px] text-muted-foreground"
              >
                ?
              </span>
            </div>
            <Input
              value={syncQuery}
              onChange={(event) => setSyncQuery(event.target.value)}
              placeholder="java or nodejs | remote or 远程 or 杭州 | 90"
            />
            <p className="mt-1.5 text-[11px] text-muted-foreground">
              查询框决定捞什么；打分与质量在「我的 · 系统规则」。保存后作为该渠道默认查询。
            </p>
            <div className="mt-3 flex gap-2">
              <Input
                value={presetName}
                onChange={(event) => setPresetName(event.target.value)}
                placeholder="预设名称，如：Java 远程"
                className="min-w-0 flex-1"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={presetSaving || !presetName.trim() || !syncQuery.trim()}
                onClick={savePreset}
              >
                {editingPresetId ? "保存修改" : "存为预设"}
              </Button>
              {editingPresetId && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => { setEditingPresetId(null); setPresetName(""); }}
                >
                  取消
                </Button>
              )}
            </div>
            {presets.length > 0 && (
              <div className="mt-3 border border-border">
                <div className="border-b border-border px-3 py-2 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                  查询预设 · {presets.length}
                </div>
                <div className="max-h-40 overflow-y-auto">
                  {presets.map((preset) => (
                    <div key={preset.id} className="flex items-center gap-2 border-b border-border px-3 py-2 last:border-b-0">
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left"
                        onClick={() => setSyncQuery(preset.query)}
                      >
                        <p className="truncate text-xs font-medium">{preset.name}</p>
                        <p className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">{preset.query}</p>
                      </button>
                      <button
                        type="button"
                        className="font-mono text-[10px] text-muted-foreground hover:text-foreground"
                        onClick={() => {
                          setSyncQuery(preset.query);
                          setPresetName(preset.name);
                          setEditingPresetId(preset.id);
                        }}
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        className="font-mono text-[10px] text-destructive"
                        onClick={() => void deletePreset(preset)}
                      >
                        删除
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium">手动数据同步</p>
              <p className="mt-1 text-[11px] text-muted-foreground">重复数据自动更新，不会重复入库</p>
            </div>
            <Button onClick={syncRecent} disabled={saving || syncing || !enabled || !syncQuery.trim()} size="sm">
              {syncing ? "拉取中…" : "按查询拉取"}
            </Button>
          </div>

          {syncRun && (
            <div className="mt-3 border border-border bg-background/70">
              <div className="flex items-center justify-between border-b border-border px-3 py-2">
                <span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                  <span className={syncing ? "size-1.5 animate-pulse rounded-full bg-primary" : syncRun.status === "succeeded" ? "size-1.5 rounded-full bg-primary" : "size-1.5 rounded-full bg-destructive"} />
                  任务 #{syncRun.id} · {syncRun.status === "queued" ? "排队中" : syncRun.status === "running" ? "运行中" : syncRun.status === "succeeded" ? "成功" : "失败"}
                </span>
                <span className="font-mono text-[10px] text-muted-foreground">
                  {new Date(syncRun.created_at).toLocaleString()}
                </span>
              </div>
              <div className="max-h-36 overflow-y-auto px-3 py-2 font-mono text-[11px] leading-6 text-muted-foreground">
                {syncRun.logs.map((log, index) => (
                  <p key={`${index}-${log.at}`}>
                    [{new Date(log.at).toLocaleTimeString()}] {log.message}
                  </p>
                ))}
              </div>
              {!syncing && (
                <div className={syncRun.status === "succeeded" ? "border-t border-primary/25 bg-primary/5 px-3 py-2 text-xs text-primary" : "border-t border-destructive/25 bg-destructive/5 px-3 py-2 text-xs text-destructive"}>
                  {syncRun.status === "succeeded" ? (
                    <div className="space-y-1">
                      <p className="font-semibold">拉取成功</p>
                      <p>本次处理 {syncRun.pulled} 条职位。</p>
                      <p>覆盖范围：{syncRun.coverage}</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <p className="font-semibold">拉取失败</p>
                      <div>
                        <p className="font-semibold">发生了什么</p>
                        <p className="mt-0.5 text-foreground">{syncRun.error || "任务异常终止，后端没有返回具体原因。"}</p>
                      </div>
                      <div>
                        <p className="font-semibold">怎么处理</p>
                        <p className="mt-0.5 text-foreground">{FAILURE_ACTION[channelId] || "检查渠道配置和网络连接后重新拉取。"}</p>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
