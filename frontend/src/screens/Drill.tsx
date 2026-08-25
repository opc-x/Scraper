import { AppHeader } from "@/components/shell/AppHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { DrillSearchCard } from "@/components/drill/DrillSearchCard";
import { DrillResultCard } from "@/components/drill/DrillResultCard";
import { useDrillSearch } from "@/hooks/useDrillSearch";

export function Drill() {
  const { videos, loading, searched, error, nextToken, search, loadMore } = useDrillSearch();

  return (
    <>
      <AppHeader title="实战" subtitle="英语面试素材" />
      <div className="flex flex-col gap-4 px-4">
        <DrillSearchCard onSearch={search} loading={loading} />

        {loading && videos.length === 0 && (
          <div className="flex flex-col gap-2">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        )}

        {error && <EmptyState message={`搜索失败：${error}`} />}

        {!loading && searched && videos.length === 0 && !error && <EmptyState message="没有找到相关视频" />}

        {!searched && !loading && <EmptyState message="搜个关键词，或者点上面的预设标签" />}

        <div className="flex flex-col gap-2">
          {videos.map((v) => (
            <DrillResultCard key={v.id} video={v} />
          ))}
        </div>

        {searched && nextToken && (
          <Button variant="outline" disabled={loading} onClick={loadMore} className="mb-4">
            {loading ? "加载中…" : "加载更多"}
          </Button>
        )}
      </div>
    </>
  );
}
