const TIERS = [
  { min: 85, className: "text-primary" },
  { min: 65, className: "text-warning" },
  { min: 40, className: "text-muted-foreground" },
  { min: -Infinity, className: "text-destructive" },
];

export function ScoreBadge({ score }: { score: number }) {
  if (score < 0) return null;
  const tier = TIERS.find((t) => score >= t.min)!;
  return <span className={`font-mono text-[13px] font-bold ${tier.className}`}>[{score}]</span>;
}
