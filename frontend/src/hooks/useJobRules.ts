import * as React from "react";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api";
import type { JobRule, JobRuleListResponse } from "@/lib/types";

export type JobRuleInput = {
  category: string;
  key: string;
  label: string;
  pattern: string;
  weight: number;
  severity: string;
  enabled: boolean;
  rationale: string;
  config: Record<string, unknown>;
  sort_order: number;
};

export function useJobRules() {
  const [rules, setRules] = React.useState<JobRule[]>([]);
  const [categories, setCategories] = React.useState<string[]>([]);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(() => {
    setLoading(true);
    apiGet<JobRuleListResponse>("/api/job-rules")
      .then((res) => {
        setRules(res.rules);
        setCategories(res.categories);
      })
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(() => load(), [load]);

  const create = React.useCallback(async (body: JobRuleInput) => {
    const row = await apiPost<JobRule>("/api/job-rules", body);
    setRules((prev) => [...prev, row].sort((a, b) => a.category.localeCompare(b.category) || a.sort_order - b.sort_order || a.id - b.id));
    return row;
  }, []);

  const update = React.useCallback(async (id: number, body: Partial<JobRuleInput>) => {
    const row = await apiPut<JobRule>(`/api/job-rules/${id}`, body);
    setRules((prev) => prev.map((r) => (r.id === id ? row : r)));
    return row;
  }, []);

  const remove = React.useCallback(async (id: number) => {
    await apiDelete(`/api/job-rules/${id}`);
    setRules((prev) => prev.filter((r) => r.id !== id));
  }, []);

  return { rules, categories, loading, create, update, remove, reload: load };
}
