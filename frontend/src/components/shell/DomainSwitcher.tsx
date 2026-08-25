import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const DOMAINS = [
  { key: "job", label: "海外职位挖掘", status: "current" as const },
  { key: "product", label: "商品数据挖掘", status: "soon" as const },
  { key: "company", label: "企业信息挖掘", status: "soon" as const },
  { key: "news", label: "舆情资讯挖掘", status: "soon" as const },
];

export function DomainSwitcher() {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 border border-border-strong px-2 py-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground hover:text-foreground"
      >
        <span className="text-primary">◎</span> 海外职位
        <ChevronDown size={11} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="absolute right-0 top-[calc(100%+6px)] z-50 w-52 border border-border-strong bg-card p-1">
          {DOMAINS.map((d) => (
            <button
              key={d.key}
              type="button"
              disabled={d.status === "soon"}
              onClick={() => setOpen(false)}
              className={cn(
                "flex w-full items-center justify-between gap-2 px-2.5 py-2 text-left font-mono text-[11px]",
                d.status === "current" ? "text-primary" : "text-muted-foreground-dim disabled:cursor-default",
              )}
            >
              <span>{d.label}</span>
              <span className="font-mono text-[9px] uppercase tracking-wide">
                {d.status === "current" ? "当前" : "待接入"}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
