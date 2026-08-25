import * as React from "react";
import { apiGet } from "@/lib/api";
import type { BoardInfo, ChannelListItem, ChannelSchemaEntry, ChannelStatusEntry } from "@/lib/types";

export function useChannelList() {
  const [data, setData] = React.useState<ChannelListItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const load = React.useCallback(() => {
    setLoading(true);
    apiGet<{ channels: ChannelListItem[] }>("/api/channels")
      .then((res) => setData(res.channels))
      .finally(() => setLoading(false));
  }, []);
  React.useEffect(() => load(), [load]);
  return { data, loading, reload: load };
}

export function useChannelSchema() {
  const [schema, setSchema] = React.useState<Record<string, ChannelSchemaEntry>>({});
  const [boards, setBoards] = React.useState<Record<string, BoardInfo>>({});
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    apiGet<{ schema: Record<string, ChannelSchemaEntry>; boards: Record<string, BoardInfo> }>("/api/channels/schema")
      .then((res) => {
        setSchema(res.schema);
        setBoards(res.boards);
      })
      .finally(() => setLoading(false));
  }, []);
  return { schema, boards, loading };
}

export function useChannelConfigValues() {
  const [values, setValues] = React.useState<Record<string, Record<string, unknown>>>({});
  const [loading, setLoading] = React.useState(true);
  const load = React.useCallback(() => {
    setLoading(true);
    apiGet<{ channels: Record<string, Record<string, unknown>> }>("/api/channels/config")
      .then((res) => setValues(res.channels))
      .finally(() => setLoading(false));
  }, []);
  React.useEffect(() => load(), [load]);
  return { values, loading, reload: load };
}

export function useChannelStatus() {
  const [status, setStatus] = React.useState<Record<string, ChannelStatusEntry>>({});
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    apiGet<{ channels: Record<string, ChannelStatusEntry> }>("/api/channels/status")
      .then((res) => setStatus(res.channels))
      .finally(() => setLoading(false));
  }, []);
  return { status, loading };
}
