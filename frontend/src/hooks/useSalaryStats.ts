import * as React from "react";
import { apiGet } from "@/lib/api";
import type { SalaryStats } from "@/lib/types";

export function useSalaryStats() {
  const [data, setData] = React.useState<SalaryStats | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    apiGet<SalaryStats>("/api/jobs/salary-stats")
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { data, loading };
}
