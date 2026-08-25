import * as React from "react";
import { apiGet, apiPost } from "@/lib/api";
import type { MarkIndex, MarkState } from "@/lib/types";
import { useToast } from "@/components/ui/toast";

interface MarkTarget {
  id: number;
  channel: string;
  external_id: string;
}

interface MarksContextValue {
  saved: Set<string>;
  archived: Set<string>;
  read: Set<string>;
  ready: boolean;
  keyOf: (t: Pick<MarkTarget, "channel" | "external_id">) => string;
  isSaved: (t: Pick<MarkTarget, "channel" | "external_id">) => boolean;
  isArchived: (t: Pick<MarkTarget, "channel" | "external_id">) => boolean;
  toggleSave: (t: MarkTarget) => Promise<MarkState | null>;
  toggleArchive: (t: MarkTarget) => Promise<MarkState | null>;
  refresh: () => Promise<void>;
}

const MarksContext = React.createContext<MarksContextValue | null>(null);

export function useMarks() {
  const ctx = React.useContext(MarksContext);
  if (!ctx) throw new Error("useMarks must be used inside <MarksProvider>");
  return ctx;
}

const keyOf = (t: Pick<MarkTarget, "channel" | "external_id">) => `${t.channel}:${t.external_id}`;

export function MarksProvider({ children }: { children: React.ReactNode }) {
  const [saved, setSaved] = React.useState<Set<string>>(new Set());
  const [archived, setArchived] = React.useState<Set<string>>(new Set());
  const [read, setRead] = React.useState<Set<string>>(new Set());
  const [ready, setReady] = React.useState(false);
  const toast = useToast();

  const refresh = React.useCallback(async () => {
    try {
      const idx = await apiGet<MarkIndex>("/api/marks/index");
      setSaved(new Set(idx.saved));
      setArchived(new Set(idx.archived));
      setRead(new Set(idx.read));
    } finally {
      setReady(true);
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  const setState = React.useCallback(
    (key: string, next: MarkState | null) => {
      setSaved((prev) => {
        const s = new Set(prev);
        next === "saved" ? s.add(key) : s.delete(key);
        return s;
      });
      setArchived((prev) => {
        const s = new Set(prev);
        next === "archived" ? s.add(key) : s.delete(key);
        return s;
      });
    },
    [],
  );

  const applyMark = React.useCallback(
    async (target: MarkTarget, state: MarkState, successText: string) => {
      const key = keyOf(target);
      const wasSaved = saved.has(key);
      const wasArchived = archived.has(key);
      const prevState: MarkState | null = wasSaved ? "saved" : wasArchived ? "archived" : null;
      const optimisticNext: MarkState | null = prevState === state ? null : state;
      setState(key, optimisticNext);
      try {
        const res = await apiPost<{ state: MarkState | null }>("/api/marks", {
          job_id: target.id,
          state,
        });
        setState(key, res.state);
        if (res.state) toast(successText, "success");
        return res.state;
      } catch {
        setState(key, prevState);
        toast("操作失败，请重试", "error");
        return prevState;
      }
    },
    [saved, archived, setState, toast],
  );

  const value: MarksContextValue = {
    saved,
    archived,
    read,
    ready,
    keyOf,
    isSaved: (t) => saved.has(keyOf(t)),
    isArchived: (t) => archived.has(keyOf(t)),
    toggleSave: (t) => applyMark(t, "saved", "已收藏"),
    toggleArchive: (t) => applyMark(t, "archived", "已归档"),
    refresh,
  };

  return <MarksContext.Provider value={value}>{children}</MarksContext.Provider>;
}
