import * as React from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const PRESETS = [
  { label: "系统设计 mock", q: "staff engineer system design mock interview" },
  { label: "分布式 / Kafka / Flink", q: "distributed systems kafka flink interview deep dive" },
  { label: "EM behavioral", q: "engineering manager behavioral mock interview" },
  { label: "Java 架构面试", q: "java backend architecture interview english" },
];

interface DrillSearchCardProps {
  onSearch: (q: string) => void;
  loading: boolean;
}

export function DrillSearchCard({ onSearch, loading }: DrillSearchCardProps) {
  const [text, setText] = React.useState("");

  const submit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (text.trim()) onSearch(text.trim());
  };

  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={submit} className="flex gap-2">
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="搜索英语面试素材，比如 system design interview"
          className="flex-1"
        />
        <Button type="submit" size="icon" disabled={loading} aria-label="搜索">
          <Search size={16} />
        </Button>
      </form>
      <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 [scrollbar-width:none]">
        {PRESETS.map((p) => (
          <button
            key={p.q}
            type="button"
            onClick={() => {
              setText(p.q);
              onSearch(p.q);
            }}
            className="shrink-0"
          >
            <Badge variant="outline" className="cursor-pointer whitespace-nowrap">
              {p.label}
            </Badge>
          </button>
        ))}
      </div>
    </div>
  );
}
