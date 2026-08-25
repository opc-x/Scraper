import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-none border px-2 py-1 font-mono text-[10px] uppercase tracking-wide transition-colors",
  {
    variants: {
      variant: {
        default: "bg-primary/15 text-primary border-primary/30",
        secondary: "bg-transparent text-foreground/80 border-border-strong",
        outline: "bg-transparent text-muted-foreground border-border-strong",
        info: "bg-info/15 text-info border-info/30",
        warning: "bg-warning/15 text-warning border-warning/30",
        destructive: "bg-destructive/15 text-destructive border-destructive/30",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
