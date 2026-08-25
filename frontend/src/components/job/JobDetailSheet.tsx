import * as React from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { X, Star, Archive, ChevronDown } from "lucide-react";
import { OriginButton } from "@/components/job/OriginButton";
import { JobAskPanel } from "@/components/job/JobAskPanel";
import { TagChipRow } from "@/components/job/TagChipRow";
import { ValueTagPicker } from "@/components/job/ValueTagPicker";
import { ScoreBadge } from "@/components/job/ScoreBadge";
import { apiGet, apiPost } from "@/lib/api";
import type { JobDetail } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useMarks } from "@/contexts/MarksProvider";
import { displayField, formatRelativeTime, formatSalaryUsd } from "@/lib/format";
import { cn } from "@/lib/utils";

function Pane({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border-t border-border pt-4">
      <h4 className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">
        {title}
      </h4>
      {children}
    </section>
  );
}

function FactRow({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div className="grid grid-cols-[5.5rem_1fr] gap-x-3 gap-y-1 text-sm">
      <dt className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="leading-relaxed text-foreground/90">{value}</dd>
    </div>
  );
}

/** 轻量正文排版：识别 ## 标题、- 列表，其余按段落。 */
function FormattedBody({ text }: { text: string }) {
  const blocks = React.useMemo(() => {
    const lines = text.replace(/\r\n/g, "\n").split("\n");
    const out: { type: "h" | "p" | "ul"; text?: string; items?: string[] }[] = [];
    let para: string[] = [];
    let bullets: string[] = [];

    const flushPara = () => {
      const body = para.join("\n").trim();
      if (body) out.push({ type: "p", text: body });
      para = [];
    };
    const flushUl = () => {
      if (bullets.length) out.push({ type: "ul", items: bullets });
      bullets = [];
    };

    for (const line of lines) {
      const heading = line.match(/^#{1,3}\s+(.+)$/) || line.match(/^【(.+)】\s*$/);
      const bullet = line.match(/^\s*[-*•]\s+(.+)$/);
      if (heading) {
        flushUl();
        flushPara();
        out.push({ type: "h", text: heading[1].trim() });
      } else if (bullet) {
        flushPara();
        bullets.push(bullet[1].trim());
      } else if (!line.trim()) {
        flushUl();
        flushPara();
      } else {
        flushUl();
        para.push(line);
      }
    }
    flushUl();
    flushPara();
    return out;
  }, [text]);

  return (
    <div className="flex flex-col gap-2.5 text-sm leading-relaxed text-foreground/90">
      {blocks.map((b, i) => {
        if (b.type === "h") {
          return (
            <h5 key={i} className="mt-1 font-heading text-[13px] font-semibold text-foreground">
              {b.text}
            </h5>
          );
        }
        if (b.type === "ul") {
          return (
            <ul key={i} className="list-disc space-y-1 pl-4">
              {b.items!.map((item, j) => (
                <li key={j}>{item}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i} className="whitespace-pre-wrap">
            {b.text}
          </p>
        );
      })}
    </div>
  );
}

export function JobDetailSheet() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { isSaved, isArchived, toggleSave, toggleArchive } = useMarks();
  const [job, setJob] = React.useState<JobDetail | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [factsOpen, setFactsOpen] = React.useState(true);
  const [confirmArchive, setConfirmArchive] = React.useState(false);
  const hasBackground = Boolean((location.state as { backgroundLocation?: unknown } | null)?.backgroundLocation);

  const load = React.useCallback(() => {
    if (!id) return;
    setLoading(true);
    apiGet<JobDetail>(`/api/jobs/${id}`)
      .then(setJob)
      .finally(() => setLoading(false));
  }, [id]);

  React.useEffect(() => {
    load();
  }, [load]);

  React.useEffect(() => {
    if (id) apiPost(`/api/jobs/${id}/read`).catch(() => {});
  }, [id]);

  const close = () => {
    if (hasBackground) navigate(-1);
    else navigate("/data", { replace: true });
  };
  const goToDataList = () => navigate("/data", { replace: true });
  const target = job ? { id: job.id, channel: job.channel, external_id: job.external_id } : null;

  const company = job ? displayField(job.company) : "";
  const city = job ? displayField(job.city) : "";
  const metaBits = job
    ? [company, job.is_remote ? "远程" : "", city && !/^远程$/i.test(city) ? city : "", job.district]
        .filter(Boolean)
    : [];
  const usdLine = job ? formatSalaryUsd(job.salary_min_usd, job.salary_max_usd, job.salary_bucket) : "";
  const verdict = job?.profile?.verdict;
  const fitScore = job?.profile?.fit_score ?? (job && job.match_score >= 0 ? job.match_score : null);
  const oneLiner = job?.profile?.one_liner;
  const posted = job ? formatRelativeTime(job.posted_at) : "";
  const companyLine = job
    ? [job.industry, job.stage, job.scale].filter(Boolean).join(" · ")
    : "";

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      <ConfirmDialog
        open={confirmArchive}
        title="归档这个职位？"
        description="归档后不再出现在职位列表，可在「我的」里找回。"
        confirmText="归档"
        cancelText="取消"
        onCancel={() => setConfirmArchive(false)}
        onConfirm={async () => {
          if (!target) return;
          setConfirmArchive(false);
          const next = await toggleArchive(target);
          if (next === "archived") goToDataList();
        }}
      />
      <header
        className="flex items-center justify-between gap-3 border-b border-border px-4 pb-3"
        style={{ paddingTop: "calc(14px + env(safe-area-inset-top, 0px))" }}
      >
        <Button variant="ghost" size="icon-sm" onClick={close} aria-label="关闭">
          <X size={18} />
        </Button>
        {job && (
          <div className="flex items-center gap-2">
            <OriginButton job={{ channel: job.channel, external_id: job.external_id, url: job.url }} className="text-primary" />
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => {
                if (!target) return;
                const next = await toggleSave(target);
                if (next === "saved") close();
              }}
              className={cn("gap-1.5", target && isSaved(target) && "text-primary")}
            >
              <Star size={15} fill={target && isSaved(target) ? "currentColor" : "none"} />
              收藏
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => {
                if (!target) return;
                if (isArchived(target)) {
                  await toggleArchive(target);
                  return;
                }
                setConfirmArchive(true);
              }}
              className={cn("gap-1.5", target && isArchived(target) && "text-muted-foreground")}
            >
              <Archive size={15} fill={target && isArchived(target) ? "currentColor" : "none"} />
              归档
            </Button>
          </div>
        )}
      </header>

      {loading && (
        <div className="flex flex-col gap-3 px-4 py-4">
          <Skeleton className="h-7 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      {!loading && !job && <p className="px-4 py-4 text-sm text-muted-foreground">职位不存在或已被删除。</p>}

      {!loading && job && (
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <section
            className={cn(
              "flex min-h-0 flex-col overflow-y-auto border-b border-border md:h-full md:w-[40%] md:flex-none md:border-b-0 md:border-r",
              factsOpen ? "flex-1" : "shrink-0",
            )}
          >
            <div className="flex flex-col gap-3 px-4 py-4">
              {metaBits.length > 0 && (
                <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                  {metaBits.join(" · ")}
                </p>
              )}
              <h1 className="font-heading text-xl font-extrabold leading-tight tracking-tight">{job.title}</h1>

              <div className="flex flex-col gap-0.5">
                {job.salary_cny && (
                  <p className="font-mono text-lg font-bold text-primary">{job.salary_cny}</p>
                )}
                <div className="flex flex-wrap items-end gap-x-3 gap-y-1">
                  {job.salary && (
                    <p className={cn("font-mono", job.salary_cny ? "text-[13px] text-muted-foreground" : "text-lg font-bold text-primary")}>
                      {job.salary}
                    </p>
                  )}
                  {usdLine && !job.salary_cny && (
                    <p className="font-mono text-[12px] text-muted-foreground">{usdLine}</p>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {verdict && (
                  <Badge variant="default" className="bg-primary/15 text-primary">
                    {verdict}
                  </Badge>
                )}
                {fitScore != null && <ScoreBadge score={fitScore} />}
                <span className="font-mono text-[11px] text-muted-foreground" title="价值观分">
                  V{job.value_score}
                </span>
                {posted && (
                  <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground-dim">
                    {posted}
                  </span>
                )}
                <Badge variant="outline" className="text-muted-foreground">
                  {job.channel}
                </Badge>
                {job.source_label && job.source_label.toLowerCase() !== job.channel.toLowerCase() && (
                  <Badge variant="info" title="来源 server / 频道">
                    {job.source_label}
                  </Badge>
                )}
              </div>

              {oneLiner && <p className="text-[13px] leading-relaxed text-foreground/80">{oneLiner}</p>}

              <div className="flex flex-wrap gap-1.5">
                {job.experience && <Badge variant="outline">{job.experience}</Badge>}
                {job.education && <Badge variant="outline">{job.education}</Badge>}
                {job.skills.slice(0, 10).map((s) => (
                  <Badge key={s} variant="secondary">
                    {s}
                  </Badge>
                ))}
              </div>
              <TagChipRow
                channel={job.channel}
                sourceLabel={job.source_label}
                skills={[]}
                isRemote={job.is_remote}
                city={job.city}
                interestTags={[]}
                valueTags={job.value_tags}
              />
            </div>

            <button
              type="button"
              className="flex items-center justify-between px-4 pb-3 font-mono text-[11px] uppercase tracking-widest text-muted-foreground md:hidden"
              onClick={() => setFactsOpen((v) => !v)}
            >
              [ {factsOpen ? "收起职位" : "展开职位"} ]
              <ChevronDown size={14} className={cn("transition-transform", factsOpen && "rotate-180")} />
            </button>

            <div className={cn("flex-col gap-1 px-4 pb-6", factsOpen ? "flex" : "hidden md:flex")}>
              {(companyLine || job.recruiter) && (
                <Pane title="公司">
                  <dl className="flex flex-col gap-2">
                    <FactRow label="概况" value={companyLine} />
                    <FactRow label="招聘官" value={job.recruiter} />
                  </dl>
                </Pane>
              )}

              {job.welfare.length > 0 && (
                <Pane title="福利">
                  <div className="flex flex-wrap gap-1.5">
                    {job.welfare.map((w) => (
                      <Badge key={w} variant="outline">
                        {w}
                      </Badge>
                    ))}
                  </div>
                </Pane>
              )}

              <Pane title={job.sections.length > 0 ? "职位正文" : job.has_real_jd ? "职位正文" : "列表摘要"}>
                {job.sections.length > 0 ? (
                  <div className="flex flex-col gap-4">
                    {job.sections.map((s) => (
                      <div key={s.title} className="flex flex-col gap-1.5">
                        <h5 className="font-heading text-[13px] font-semibold text-foreground">{s.title}</h5>
                        <FormattedBody text={s.body} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <>
                    <FormattedBody text={job.description || "这条还没有岗位职责正文。"} />
                    {!job.has_real_jd && (
                      <p className="mt-2 text-xs text-muted-foreground">
                        列表接口没有完整 JD。点右上角原文看完整要求。
                      </p>
                    )}
                  </>
                )}
              </Pane>

              {job.company_intro && (
                <Pane title="公司简介">
                  <FormattedBody text={job.company_intro} />
                </Pane>
              )}

              <Pane title="标签">
                <ValueTagPicker jobId={job.id} library={job.value_tag_library} onChanged={load} />
              </Pane>
            </div>
          </section>

          <JobAskPanel jobId={job.id} fillRemaining={!factsOpen} />
        </div>
      )}
    </div>
  );
}
