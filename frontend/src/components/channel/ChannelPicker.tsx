import * as React from "react";
import { ChevronDown, ChevronRight, ChevronUp, RefreshCw } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { ChannelConfigForm } from "@/components/channel/ChannelConfigForm";
import { useChannelList, useChannelSchema } from "@/hooks/useChannels";
import type { ChannelListItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { apiPost } from "@/lib/api";
import { useToast } from "@/components/ui/toast";

const STATUS_LABEL: Record<ChannelListItem["status"], string> = {
  active: "已启用",
  missing_config: "待配置",
  disabled: "未启用",
};

const STATUS_COLOR: Record<ChannelListItem["status"], string> = {
  active: "text-primary",
  missing_config: "text-warning",
  disabled: "text-muted-foreground-dim",
};

const SYNC_CHANNELS = new Set(["boss", "telegram", "discord", "x", "x_zh", "v2ex", "eleduck"]);

function ChannelRow({ channel, onOpen, onSynced }: { channel: ChannelListItem; onOpen: () => void; onSynced: () => void }) {
  const [expanded, setExpanded] = React.useState(false);
  const [overflowing, setOverflowing] = React.useState(false);
  const descriptionRef = React.useRef<HTMLParagraphElement>(null);
  const [syncing, setSyncing] = React.useState(false);
  const toast = useToast();

  const sync = async (event: React.MouseEvent) => {
    event.stopPropagation();
    if (channel.status !== "active" || !(channel.sync_supported ?? SYNC_CHANNELS.has(channel.id))) return;
    setSyncing(true);
    try {
      const result = await apiPost<{ pulled: number; coverage: string }>(`/api/channels/${channel.id}/sync`, {});
      toast(`拉取完成：${result.pulled} 条 · ${result.coverage}`, "success");
      onSynced();
    } catch (error) {
      toast(error instanceof Error ? error.message : "拉取失败", "error");
    } finally {
      setSyncing(false);
    }
  };

  React.useLayoutEffect(() => {
    const description = descriptionRef.current;
    if (!description) return;
    const measure = () => setOverflowing(description.scrollHeight > description.clientHeight + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(description);
    return () => observer.disconnect();
  }, [channel.description, expanded]);

  return (
    <div
      onClick={onOpen}
      className="flex cursor-pointer items-start gap-3 border-b border-border bg-card px-3.5 py-3 text-left transition-colors last:border-b-0 active:bg-card-foreground/5"
    >
      <span
        className={cn(
          "mt-2 size-1.5 shrink-0 rounded-full",
          channel.status === "active" && "bg-primary",
          channel.status === "missing_config" && "bg-warning",
          channel.status === "disabled" && "border border-muted-foreground-dim",
        )}
        style={channel.status === "active" ? { boxShadow: "0 0 6px var(--primary)" } : undefined}
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{channel.name}</p>
        <p ref={descriptionRef} className={cn("text-xs leading-5 text-muted-foreground", !expanded && "line-clamp-2")}>
          {channel.description}
        </p>
        {channel.last_sync && (
          <p className={cn("mt-1 font-mono text-[10px]", channel.last_sync.status === "failed" ? "text-destructive" : "text-muted-foreground")}>
            最近同步：{channel.last_sync.status === "queued" ? "排队中" : channel.last_sync.status === "running" ? "运行中" : channel.last_sync.status === "succeeded" ? `成功 ${channel.last_sync.pulled} 条` : "失败"}
            {channel.last_sync.finished_at ? ` · ${new Date(channel.last_sync.finished_at).toLocaleString()}` : ""}
          </p>
        )}
        {overflowing && (
          <button
            type="button"
            className="mt-1 flex items-center gap-1 font-mono text-[10px] text-muted-foreground hover:text-foreground"
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
      <button
        type="button"
        onClick={sync}
        disabled={syncing || channel.status !== "active" || !(channel.sync_supported ?? SYNC_CHANNELS.has(channel.id))}
        title={channel.sync_coverage}
        className="mt-0.5 flex shrink-0 items-center gap-1 border border-border px-2 py-1 font-mono text-[10px] text-primary disabled:cursor-not-allowed disabled:text-muted-foreground-dim"
      >
        <RefreshCw size={11} className={syncing ? "animate-spin" : ""} />
        {syncing ? "拉取中" : (channel.sync_supported ?? SYNC_CHANNELS.has(channel.id)) ? "拉取" : "未接入"}
      </button>
      <span className={cn("mt-1 shrink-0 font-mono text-[10px] uppercase tracking-wide", STATUS_COLOR[channel.status])}>
        {STATUS_LABEL[channel.status]}
      </span>
      <ChevronRight size={14} className="mt-1 shrink-0 text-muted-foreground-dim" />
    </div>
  );
}

export function ChannelPicker() {
  const { data: channels, loading, reload } = useChannelList();
  const { schema, boards, loading: schemaLoading } = useChannelSchema();
  const [openChannel, setOpenChannel] = React.useState<string | null>(null);
  const [showAll, setShowAll] = React.useState(false);
  const visibleChannels = showAll ? channels : channels.slice(0, 3);

  const grouped = React.useMemo(() => {
    const map = new Map<string, ChannelListItem[]>();
    for (const ch of visibleChannels) {
      const list = map.get(ch.board) ?? [];
      list.push(ch);
      map.set(ch.board, list);
    }
    return map;
  }, [visibleChannels]);

  if (loading || schemaLoading) {
    return (
      <div className="flex flex-col gap-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    );
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="font-heading text-lg font-bold">渠道管理</h2>
          <p className="mt-1 text-xs text-muted-foreground">配置、启停与重置数据渠道</p>
        </div>
        <span className="font-mono text-[10px] text-muted-foreground">共 {channels.length} 条</span>
      </div>
      {[...grouped.entries()].map(([boardId, list]) => (
        <div key={boardId} className="flex flex-col gap-0 border border-border">
          <h3 className="border-b border-border bg-card px-3.5 py-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            {boards[boardId]?.name ?? boardId}
          </h3>
          {list.map((ch) => (
            <ChannelRow
              key={ch.id}
              channel={ch}
              onOpen={() => setOpenChannel(ch.id)}
              onSynced={() => window.dispatchEvent(new Event("scraped-updated"))}
            />
          ))}
        </div>
      ))}

      {channels.length > 3 && (
        <button
          type="button"
          className="flex items-center justify-center gap-1 border border-border bg-card py-2.5 font-mono text-[11px] text-muted-foreground transition-colors hover:text-foreground"
          onClick={() => setShowAll((value) => !value)}
        >
          {showAll ? "收起" : `查看全部（${channels.length}）`}
          {showAll ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
      )}

      <Dialog open={!!openChannel} onOpenChange={(open) => !open && setOpenChannel(null)}>
        <DialogContent className="p-4">
          {openChannel && schema[openChannel] && (
            <>
              <DialogTitle className="mb-4 font-heading text-lg font-semibold">{schema[openChannel].name} 配置</DialogTitle>
              <ChannelConfigForm
                channelId={openChannel}
                schema={schema[openChannel]}
                syncSupported={SYNC_CHANNELS.has(openChannel)}
                onSaved={() => {
                  reload();
                }}
              />
            </>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
