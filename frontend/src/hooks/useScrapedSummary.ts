import * as React from "react";
import { apiGet } from "@/lib/api";
import type { ScrapedSummary } from "@/lib/types";

export function useScrapedSummary() {
  const [data, setData] = React.useState<ScrapedSummary | null>(null);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(() => {
    let cancelled = false;
    apiGet<ScrapedSummary>("/api/scraped/summary")
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

  React.useEffect(() => load(), [load]);
  React.useEffect(() => {
    const refresh = () => load();
    window.addEventListener("scraped-updated", refresh);
    return () => window.removeEventListener("scraped-updated", refresh);
  }, [load]);

  return { data, loading };
}
