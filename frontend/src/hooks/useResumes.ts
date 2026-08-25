import * as React from "react";
import { apiDelete, apiGet, apiPost, apiPut, fileToBase64 } from "@/lib/api";
import type { Resume, ResumeListResponse } from "@/lib/types";

export function useResumes() {
  const [rows, setRows] = React.useState<Resume[]>([]);
  const [loading, setLoading] = React.useState(true);

  const reload = React.useCallback(() => {
    setLoading(true);
    apiGet<ResumeListResponse>("/api/resumes")
      .then((res) => setRows(res.resumes))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(() => {
    reload();
  }, [reload]);

  const create = async (title = "未命名简历") => {
    const row = await apiPost<Resume>("/api/resumes", { title, markdown: "" });
    reload();
    return row;
  };

  const upload = async (file: File) => {
    const content_b64 = await fileToBase64(file);
    const row = await apiPost<Resume>("/api/resumes/upload", {
      filename: file.name,
      content_b64,
    });
    reload();
    return row;
  };

  const replaceOriginal = async (id: number, file: File) => {
    const content_b64 = await fileToBase64(file);
    const row = await apiPost<Resume>(`/api/resumes/${id}/original`, {
      filename: file.name,
      content_b64,
    });
    reload();
    return row;
  };

  const update = async (
    id: number,
    body: { title: string; markdown?: string; final_markdown?: string },
  ) => {
    const row = await apiPut<Resume>(`/api/resumes/${id}`, body);
    reload();
    return row;
  };

  const activate = async (id: number) => {
    await apiPost(`/api/resumes/${id}/activate`);
    reload();
  };

  const remove = async (id: number) => {
    await apiDelete(`/api/resumes/${id}`);
    reload();
  };

  const get = (id: number) => apiGet<Resume>(`/api/resumes/${id}`);

  return { rows, loading, reload, create, upload, replaceOriginal, update, activate, remove, get };
}
