import { cn } from "@/lib/utils";

export interface FilterChipOption {
  value: string;
  label: string;
}

interface FilterChipRowProps {
  options: FilterChipOption[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

export function FilterChipRow({ options, value, onChange, className }: FilterChipRowProps) {
  return (
    <div className={cn("-mx-4 flex gap-1.5 overflow-x-auto px-4 [scrollbar-width:none]", className)}>
      {options.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={cn(
              "shrink-0 whitespace-nowrap border px-2.5 py-1.5 font-mono text-[11px] uppercase tracking-wide transition-colors",
              active
                ? "border-primary bg-primary text-primary-foreground font-semibold"
                : "border-border-strong text-muted-foreground hover:text-foreground",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
