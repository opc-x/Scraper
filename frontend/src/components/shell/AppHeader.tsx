import type { ReactNode } from "react";
import { DomainSwitcher } from "@/components/shell/DomainSwitcher";

interface AppHeaderProps {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  live?: boolean;
}

export function AppHeader({ title, subtitle, action, live }: AppHeaderProps) {
  return (
    <header
      className="sticky top-0 z-30 flex flex-col gap-2 bg-background/90 px-4 pb-3 backdrop-blur-lg"
      style={{ paddingTop: "calc(14px + env(safe-area-inset-top, 0px))" }}
    >
      <div className="flex items-center justify-between gap-3">
        <h1 className="truncate font-heading text-[22px] font-extrabold leading-tight tracking-tight">{title}</h1>
        <DomainSwitcher />
      </div>
      {(subtitle || live || action) && (
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            {live && (
              <div className="flex shrink-0 items-center gap-2">
                <span className="size-1.5 rounded-full bg-primary" style={{ boxShadow: "0 0 6px var(--primary)" }} />
                <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">live feed</span>
              </div>
            )}
            {subtitle && <p className="truncate font-mono text-[11px] text-muted-foreground">{subtitle}</p>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
    </header>
  );
}
