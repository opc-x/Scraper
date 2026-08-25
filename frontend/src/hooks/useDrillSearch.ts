import * as React from "react";
import { apiGet } from "@/lib/api";
import type { DrillSearchResponse, DrillVideo } from "@/lib/types";

export function useDrillSearch() {
  const [query, setQuery] = React.useState("");
  const [videos, setVideos] = React.useState<DrillVideo[]>([]);
  const [nextToken, setNextToken] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [searched, setSearched] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const run = React.useCallback(async (q: string, { append = false }: { append?: boolean } = {}) => {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiGet<DrillSearchResponse>("/api/drill/search", {
        q,
        page_token: append ? nextToken : undefined,
        max_results: 20,
      });
      setVideos((prev) => (append ? [...prev, ...res.videos] : res.videos));
      setNextToken(res.next_page_token);
      setSearched(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "搜索失败");
    } finally {
      setLoading(false);
    }
  }, [nextToken]);

  const search = React.useCallback(
    (q: string) => {
      setQuery(q);
      run(q, { append: false });
    },
    [run],
  );

  const loadMore = React.useCallback(() => {
    if (query) run(query, { append: true });
  }, [query, run]);

  return { query, videos, nextToken, loading, searched, error, search, loadMore };
}
