import * as React from "react";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api";
import type { ValueTag } from "@/lib/types";

export function useValueTags() {
  const [tags, setTags] = React.useState<ValueTag[]>([]);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(() => {
    setLoading(true);
    apiGet<{ tags: ValueTag[] }>("/api/value-tags")
      .then((res) => setTags(res.tags))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(() => load(), [load]);

  const draft = React.useCallback(async (description: string, category: string, polarity: -1 | 0 | 1) => {
    const tag = await apiPost<ValueTag>("/api/value-tags/draft", { description, category, polarity });
    setTags((prev) => [tag, ...prev]);
    return tag;
  }, []);

  const update = React.useCallback(async (id: number, fields: Pick<ValueTag, "label" | "pattern" | "polarity" | "weight">) => {
    const tag = await apiPut<ValueTag>(`/api/value-tags/${id}`, fields);
    setTags((prev) => prev.map((t) => (t.id === id ? tag : t)));
    return tag;
  }, []);

  const approve = React.useCallback(async (id: number) => {
    const tag = await apiPost<ValueTag>(`/api/value-tags/${id}/approve`);
    setTags((prev) => prev.map((t) => (t.id === id ? tag : t)));
  }, []);

  const unapprove = React.useCallback(async (id: number) => {
    const tag = await apiPost<ValueTag>(`/api/value-tags/${id}/unapprove`);
    setTags((prev) => prev.map((t) => (t.id === id ? tag : t)));
  }, []);

  const remove = React.useCallback(async (id: number) => {
    await apiDelete(`/api/value-tags/${id}`);
    setTags((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const pin = React.useCallback(async (id: number) => {
    const tag = await apiPost<ValueTag>(`/api/value-tags/${id}/pin`);
    setTags((prev) => prev.map((t) => (t.id === id ? tag : t)));
  }, []);

  const unpin = React.useCallback(async (id: number) => {
    const tag = await apiPost<ValueTag>(`/api/value-tags/${id}/unpin`);
    setTags((prev) => prev.map((t) => (t.id === id ? tag : t)));
  }, []);

  return { tags, loading, draft, update, approve, unapprove, remove, pin, unpin, reload: load };
}
