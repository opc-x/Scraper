import * as React from "react";
import { Send, Sparkles } from "lucide-react";
import { apiPost, ApiError } from "@/lib/api";
import type { AskAction, AskReply } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const ACTIONS: { id: AskAction; label: string; hint: string }[] = [
  { id: "features", label: "特征提取", hint: "拆职级、技术栈、地点、节奏" },
  { id: "values", label: "价值观", hint: "按你的默认价值观打分" },
  { id: "requirements", label: "职位要求", hint: "必须 / 加分 / 隐含门槛" },
  { id: "preference", label: "偏好匹配", hint: "先写偏好，再对照 JD" },
  { id: "resume", label: "简历匹配", hint: "默认用已有简历" },
];

interface Turn {
  id: number;
  action: AskAction;
  query: string;
  reply?: AskReply;
  error?: string;
}

export function JobAskPanel({ jobId, fillRemaining = false }: { jobId: number; fillRemaining?: boolean }) {
  const toast = useToast();
  const [draft, setDraft] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [active, setActive] = React.useState<AskAction | null>(null);
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const listRef = React.useRef<HTMLDivElement>(null);
  const nextId = React.useRef(1);

  React.useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, busy]);

  const run = async (action: AskAction, message: string) => {
    if (busy) return;
    const query = message.trim();
    const id = nextId.current++;
    setActive(action);
    setBusy(true);
    setTurns((prev) => [...prev, { id, action, query }]);
    try {
      const reply = await apiPost<AskReply>(`/api/jobs/${jobId}/ask`, {
        action,
        message: query,
      });
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, reply } : t)));
      if (action !== "chat") setDraft("");
    } catch (err) {
      const text = err instanceof ApiError ? err.message : "请求失败，再试一次";
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, error: text } : t)));
      toast(text, "error");
    } finally {
      setBusy(false);
      setActive(null);
    }
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text) {
      toast("先写一句再问", "error");
      return;
    }
    void run("chat", text);
  };

  const empty = turns.length === 0 && !busy;
  // 手机竖排：没对话时不要把输入栏钉在屏幕底（中间会变成死区）；
  // 有回复后才把剩余高度交给对话。桌面左右栏仍用 spacer 把输入栏钉在右栏底部。
  const stretch = fillRemaining && !empty;

  return (
    <div className={cn("flex flex-col md:min-h-0 md:flex-1", stretch ? "min-h-0 flex-1" : "shrink-0")}>
      {!empty && (
        <div ref={listRef} className="max-h-[40vh] min-h-0 flex-1 overflow-y-auto px-4 py-3 md:max-h-none">
          <div className="flex flex-col gap-4">
            {turns.map((turn) => (
              <article key={turn.id} className="flex flex-col gap-2">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground-dim">
                  [ {ACTIONS.find((a) => a.id === turn.action)?.label || "提问"} ]
                  {turn.query ? ` · ${turn.query}` : ""}
                </p>
                {turn.reply && <AskCard reply={turn.reply} />}
                {turn.error && <p className="text-sm text-destructive">{turn.error}</p>}
                {!turn.reply && !turn.error && (
                  <p className="font-mono text-[11px] text-muted-foreground">推理中…</p>
                )}
              </article>
            ))}
          </div>
        </div>
      )}

      {empty && <div className="hidden min-h-0 md:block md:flex-1" />}

      <div className="border-t border-border bg-background/90 px-4 py-3 backdrop-blur-lg">
        {empty && (
          <div className="mb-3 flex items-start gap-2.5">
            <Sparkles size={16} className="mt-0.5 shrink-0 text-primary" />
            <div>
              <p className="font-mono text-[11px] uppercase tracking-widest text-primary">AI 看岗</p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                先点下面的动作，或直接写问题。简历默认已接上，偏好要你自己说。
              </p>
            </div>
          </div>
        )}
        <form onSubmit={onSubmit} className="flex flex-col gap-2.5">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSubmit(e);
              }
            }}
            rows={2}
            disabled={busy}
            placeholder="写偏好、问这个职位，或补充你的判断…"
            className="w-full resize-none rounded-[var(--radius-md)] border border-input bg-card/60 px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          />
          <div className="flex flex-wrap items-center gap-1.5">
            {ACTIONS.map((item) => (
              <button
                key={item.id}
                type="button"
                title={item.hint}
                disabled={busy}
                onClick={() => void run(item.id, draft)}
                className={cn(
                  "border px-2 py-1 font-mono text-[10px] uppercase tracking-wide transition-colors",
                  active === item.id
                    ? "border-primary bg-primary text-primary-foreground font-semibold"
                    : "border-border-strong text-muted-foreground hover:text-foreground",
                )}
              >
                [{item.label}]
              </button>
            ))}
            <Button type="submit" size="sm" disabled={busy} className="ml-auto">
              <Send size={12} />
              发送
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function AskCard({ reply }: { reply: AskReply }) {
  const entries = Object.entries(reply.inferred || {});
  return (
    <div
      className="flex flex-col gap-3 border border-primary/25 p-3.5"
      style={{ background: "linear-gradient(180deg, color-mix(in oklch, var(--primary) 5%, transparent), transparent 40%)" }}
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-mono text-[11px] font-bold uppercase tracking-widest text-primary">{reply.title}</h3>
        {reply.cached && <span className="font-mono text-[10px] text-muted-foreground-dim">缓存</span>}
      </div>
      {reply.score != null && (
        <div>
          <div className="flex items-center justify-between font-mono text-[10px]">
            <span className="text-muted-foreground-dim">分数</span>
            <span className="font-bold text-foreground">{reply.score} / 100</span>
          </div>
          <div className="mt-1 h-1 overflow-hidden bg-muted">
            <div
              className="h-full"
              style={{
                width: `${Math.max(0, Math.min(100, reply.score))}%`,
                background:
                  reply.score >= 65 ? "var(--primary)" : reply.score >= 40 ? "var(--warning)" : "var(--destructive)",
              }}
            />
          </div>
        </div>
      )}
      {reply.summary && <p className="text-sm leading-relaxed">{reply.summary}</p>}
      {entries.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {entries.map(([k, v]) => (
            <li key={k} className="text-sm">
              <span className="text-muted-foreground">{k} — </span>
              {v}
            </li>
          ))}
        </ul>
      )}
      {reply.bullets.length > 0 && (
        <ul className="list-inside list-disc text-sm leading-relaxed text-foreground/90">
          {reply.bullets.map((b, i) => (
            <li key={i}>{b}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
