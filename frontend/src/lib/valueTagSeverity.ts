export type Severity = "green" | "yellow" | "red";

/** 标签本身的属性色（管理页用）：加分=绿，减分=红。 */
export function tagSeverity(polarity: 1 | 0 | -1): Severity {
  if (polarity === 1) return "green";
  if (polarity === 0) return "yellow";
  return "red";
}

/** 某条职位上这个标签的命中态颜色。
 * 减分标签：命中=红，未命中=绿。
 * 加分标签：命中=绿，未命中=红（仅 pinned 标签会在未命中时出现在卡片上）。 */
export function hitSeverity(polarity: 1 | 0 | -1, matched: boolean): Severity {
  if (polarity === 0) return "yellow";
  if (polarity === -1) return matched ? "red" : "green";
  return matched ? "green" : "red";
}

export const SEVERITY_LABEL: Record<Severity, string> = { green: "绿", yellow: "黄", red: "红" };
export const SEVERITY_BADGE_VARIANT: Record<Severity, "default" | "warning" | "destructive"> = {
  green: "default",
  yellow: "warning",
  red: "destructive",
};
