import * as React from "react";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api";
import type { ResumeModelId, SopPlaybook, SopListResponse } from "@/lib/types";

export function useSops() {
  const [books, setBooks] = React.useState<SopPlaybook[]>([]);
  const [loading, setLoading] = React.useState(true);

  const reload = React.useCallback(() => {
    setLoading(true);
    apiGet<SopListResponse>("/api/sops")
      .then((res) => setBooks(res.sops))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(() => {
    reload();
  }, [reload]);

  const of = (purpose: "analyze" | "optimize") =>
    books.filter((b) => (b.purpose || "analyze") === purpose);

  const draft = (purpose: "analyze" | "optimize" = "analyze") => {
    const rows = of(purpose);
    return rows.find((b) => b.status !== "used" && b.is_active) ?? rows.find((b) => b.status !== "used") ?? null;
  };

  const generate = async (input: {
    brief: string;
    models: ResumeModelId[];
    resumeId?: number | null;
    purpose?: "analyze" | "optimize";
  }) => {
    const row = await apiPost<SopPlaybook>("/api/sops/generate", {
      brief: input.brief,
      models: input.models,
      resume_id: input.resumeId ?? null,
      purpose: input.purpose ?? "analyze",
    });
    reload();
    return row;
  };

  const update = async (
    id: number,
    patch: { name?: string; description?: string; brief?: string; models?: ResumeModelId[]; steps: SopPlaybook["steps"] },
  ) => {
    const row = await apiPut<SopPlaybook>(`/api/sops/${id}`, patch);
    reload();
    return row;
  };

  const remove = async (id: number) => {
    await apiDelete(`/api/sops/${id}`);
    reload();
  };

  return { books, of, draft, loading, reload, generate, update, remove };
}
