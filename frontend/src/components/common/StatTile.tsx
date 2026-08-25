import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface StatTileProps {
  label: string;
  value: ReactNode;
  sublabel?: string;
  variant?: "hero" | "grid" | "inline";
  onClick?: () => void;
  className?: string;
}

export function StatTile({ label, value, sublabel, variant = "grid", onClick, className }: StatTileProps) {
  const Comp = onClick ? "button" : "div";
  return (
    <Comp
      onClick={onClick}
      className={cn(
        "relative overflow-hidden border border-border bg-card px-3.5 py-3 text-left",
        variant === "hero" && "px-[18px] py-5",
        variant === "inline" && "flex items-center justify-between border-0 bg-transparent px-0 py-1.5",
        onClick && "transition-colors active:bg-card-foreground/5",
        className,
      )}
    >
      {variant === "hero" && (
        <div
          className="pointer-events-none absolute -right-6 -top-6 size-32 rounded-full opacity-20"
          style={{ background: "radial-gradient(circle, var(--primary), transparent 70%)" }}
        />
      )}
      <p className={cn("font-mono text-[10px] uppercase tracking-wider text-muted-foreground", variant === "hero" && "text-[11px]")}>
        {label}
      </p>
      <p
        className={cn(
          "font-mono font-bold leading-tight tracking-tight text-foreground",
          variant === "hero" ? "text-[44px]" : "text-lg",
          variant === "inline" && "text-base",
        )}
      >
        {value}
      </p>
      {sublabel && (
        <div className="mt-1.5 flex items-center gap-1.5">
          <span className="size-1.5 rounded-full bg-primary" style={{ boxShadow: "0 0 6px var(--primary)" }} />
          <p className="font-mono text-[11px] text-primary">{sublabel}</p>
        </div>
      )}
    </Comp>
  );
}
