import * as React from "react";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api";
import type { ResumeAnalysis, ResumeModelId, ResumeSuggestion, ResumeVersion, SuggestionStatus } from "@/lib/types";

interface SuggestionList {
  suggestions: ResumeSuggestion[];
  total: number;
}

interface AnalysisList {
  analyses: ResumeAnalysis[];
  total: number;
}

interface VersionList {
  versions: ResumeVersion[];
  total: number;
}

export function useResumeLoop(resumeId: number | null) {
  const [suggestions, setSuggestions] = React.useState<ResumeSuggestion[]>([]);
  const [analyses, setAnalyses] = React.useState<ResumeAnalysis[]>([]);
  const [versions, setVersions] = React.useState<ResumeVersion[]>([]);
  const [loading, setLoading] = React.useState(false);

  const reload = React.useCallback(() => {
    if (resumeId == null) {
      setSuggestions([]);
      setAnalyses([]);
      setVersions([]);
      return;
    }
    setLoading(true);
    Promise.all([
      apiGet<SuggestionList>(`/api/resumes/${resumeId}/suggestions`, { kind: "optimize" }),
      apiGet<AnalysisList>(`/api/resumes/${resumeId}/analyses`),
      apiGet<VersionList>(`/api/resumes/${resumeId}/versions`),
    ])
      .then(([sug, ana, ver]) => {
        setSuggestions(sug.suggestions);
        setAnalyses(ana.analyses);
        setVersions(ver.versions);
      })
      .finally(() => setLoading(false));
  }, [resumeId]);

  React.useEffect(() => {
    reload();
  }, [reload]);

  const analyze = async (
    sopId?: number | null,
    extra: { brief?: string; models?: string[]; direct?: boolean } = {},
  ) => {
    if (resumeId == null) return;
    const row = await apiPost<ResumeAnalysis>(`/api/resumes/${resumeId}/analyze`, {
      sop_id: sopId ?? null,
      brief: extra.brief ?? "",
      models: extra.models ?? [],
      direct: extra.direct ?? false,
    });
    await reload();
    return row;
  };

  const getAnalysis = (id: number) => {
    if (resumeId == null) return Promise.reject(new Error("no resume"));
    return apiGet<ResumeAnalysis>(`/api/resumes/${resumeId}/analyses/${id}`);
  };

  const renameAnalysis = async (id: number, title: string) => {
    if (resumeId == null) return;
    const row = await apiPut<ResumeAnalysis>(`/api/resumes/${resumeId}/analyses/${id}`, { title });
    setAnalyses((prev) => prev.map((a) => (a.id === row.id ? { ...a, ...row } : a)));
    return row;
  };

  const removeAnalysis = async (id: number) => {
    if (resumeId == null) return;
    await apiDelete(`/api/resumes/${resumeId}/analyses/${id}`);
    setAnalyses((prev) => prev.filter((a) => a.id !== id));
  };

  const suggest = async (
    model: ResumeModelId,
    input: { analysisId?: number | null; brief?: string; sopId?: number | null } = {},
  ) => {
    if (resumeId == null) return;
    const res = await apiPost<SuggestionList>(`/api/resumes/${resumeId}/suggest`, {
      model,
      analysis_id: input.analysisId ?? null,
      brief: input.brief ?? "",
      sop_id: input.sopId ?? null,
    });
    setSuggestions(res.suggestions);
    return res.suggestions;
  };

  const setStatus = async (id: number, status: SuggestionStatus) => {
    if (resumeId == null) return;
    const row = await apiPost<ResumeSuggestion>(`/api/resumes/${resumeId}/suggestions/${id}`, { status });
    setSuggestions((prev) => prev.map((s) => (s.id === row.id ? row : s)));
    return row;
  };

  const apply = async () => {
    if (resumeId == null) return;
    const row = await apiPost<ResumeVersion>(`/api/resumes/${resumeId}/apply`);
    await reload();
    return row;
  };

  const activate = async (versionId: number) => {
    if (resumeId == null) return;
    await apiPost(`/api/resumes/${resumeId}/versions/${versionId}/activate`);
    await reload();
  };

  const remove = async (versionId: number) => {
    if (resumeId == null) return;
    await apiDelete(`/api/resumes/${resumeId}/versions/${versionId}`);
    await reload();
  };

  return {
    suggestions,
    analyses,
    versions,
    loading,
    reload,
    analyze,
    getAnalysis,
    renameAnalysis,
    removeAnalysis,
    suggest,
    setStatus,
    apply,
    activate,
    remove,
  };
}
