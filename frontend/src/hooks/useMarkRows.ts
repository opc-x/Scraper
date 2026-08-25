import * as React from "react";
import { apiGet } from "@/lib/api";
import type { MarkRow, MarkState } from "@/lib/types";

export function useMarkRows(state: MarkState) {
  const [rows, setRows] = React.useState<MarkRow[]>([]);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(() => {
    setLoading(true);
    apiGet<{ marks: MarkRow[] }>("/api/marks", { state })
      .then((res) => setRows(res.marks))
      .finally(() => setLoading(false));
  }, [state]);

  React.useEffect(() => {
    load();
  }, [load]);

  return { rows, loading, reload: load };
}
