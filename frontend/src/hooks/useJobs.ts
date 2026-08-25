import * as React from "react";
import { apiGet } from "@/lib/api";
import type { JobListResponse } from "@/lib/types";

export interface JobFilters {
  channel: string;
  tag: string;
  preference: string;
  sort: "match" | "posted" | "salary" | "value";
  order: "asc" | "desc";
  minScore: number | null;
  withinDays: number;
  page: number;
  pageSize: number;
  remote: boolean | null;
  valueTag: string;
  china: boolean;
}

export const DEFAULT_FILTERS: JobFilters = {
  channel: "",
  tag: "",
  preference: "",
  sort: "value",
  order: "desc",
  minScore: null,
  withinDays: 90,
  page: 1,
  pageSize: 20,
  remote: null,
  valueTag: "",
  china: false,
};

export function useJobs(filters: JobFilters) {
  const [data, setData] = React.useState<JobListResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [reloadTick, setReloadTick] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiGet<JobListResponse>("/api/scraped", {
      channel: filters.channel,
      tag: filters.tag,
      preference: filters.preference,
      sort: filters.sort,
      order: filters.order,
      min_score: filters.minScore ?? undefined,
      within_days: filters.withinDays,
      remote: filters.remote ?? undefined,
      value_tag: filters.valueTag || undefined,
      china: filters.china || undefined,
      limit: filters.pageSize,
      offset: (filters.page - 1) * filters.pageSize,
    })
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    filters.channel,
    filters.tag,
    filters.preference,
    filters.sort,
    filters.order,
    filters.minScore,
    filters.withinDays,
    filters.remote,
    filters.valueTag,
    filters.china,
    filters.page,
    filters.pageSize,
    reloadTick,
  ]);

  const refetch = React.useCallback(() => setReloadTick((t) => t + 1), []);

  return { data, loading, error, refetch };
}
