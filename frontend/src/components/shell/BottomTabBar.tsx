import { NavLink } from "react-router-dom";
import { Home, LayoutGrid, Star, User, Dumbbell } from "lucide-react";
import { cn } from "@/lib/utils";

const TABS = [
  { to: "/", label: "首页", icon: Home, end: true },
  { to: "/data", label: "数据", icon: LayoutGrid },
  { to: "/fav", label: "收藏", icon: Star },
  { to: "/drill", label: "实战", icon: Dumbbell },
  { to: "/mine", label: "我的", icon: User },
];

export function BottomTabBar() {
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 flex justify-around border-t border-border bg-background/90 px-2 pt-2 backdrop-blur-lg"
      style={{ paddingBottom: "calc(8px + env(safe-area-inset-bottom, 0px))" }}
    >
      {TABS.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            cn(
              "relative flex flex-col items-center gap-0.5 py-1 transition-colors",
              isActive ? "text-primary" : "text-muted-foreground-dim",
            )
          }
        >
          {({ isActive }) => (
            <>
              {isActive && (
                <span
                  className="absolute -top-2 h-[2px] w-6 bg-primary"
                  style={{ boxShadow: "0 0 6px var(--primary)" }}
                />
              )}
              <Icon size={19} strokeWidth={isActive ? 2 : 1.7} />
              <span className={cn("font-mono text-[9px] tracking-wide", isActive && "font-bold")}>{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
