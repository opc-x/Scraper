import type { SopStep } from "@/lib/types";

export type ResumeModelId = "claude" | "codex" | "cursor";

export const MODELS: { id: ResumeModelId; label: string }[] = [
  { id: "codex", label: "Codex" },
  { id: "cursor", label: "Cursor" },
  { id: "claude", label: "Claude" },
];

export function SopFlow({ steps }: { steps: SopStep[] }) {
  if (steps.length === 0) return null;
  return (
    <div className="flex flex-col items-stretch px-3.5 py-3">
      {steps.map((s, i) => (
        <div key={s.id || `${s.title}-${i}`}>
          <div className="border border-primary/35 bg-primary/5 px-3 py-2.5">
            <p className="text-center font-mono text-[13px] font-semibold text-foreground">{s.title}</p>
            {s.body ? (
              <p className="mt-1 text-center text-[12px] leading-relaxed text-muted-foreground">{s.body}</p>
            ) : null}
          </div>
          {i < steps.length - 1 ? <p className="py-1 text-center font-mono text-[14px] text-primary">↓</p> : null}
        </div>
      ))}
    </div>
  );
}
