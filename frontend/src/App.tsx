import { Routes, Route, useLocation } from "react-router-dom";
import { BottomTabBar } from "@/components/shell/BottomTabBar";
import { ToastProvider } from "@/components/ui/toast";
import { MarksProvider } from "@/contexts/MarksProvider";
import { Home } from "@/screens/Home";
import { Data } from "@/screens/Data";
import { Fav } from "@/screens/Fav";
import { Mine } from "@/screens/Mine";
import { Drill } from "@/screens/Drill";
import { JobDetailSheet } from "@/components/job/JobDetailSheet";
import { ManualJobSheet } from "@/components/job/ManualJobSheet";

interface LocationState {
  backgroundLocation?: Location;
}

export function App() {
  const location = useLocation();
  const state = location.state as LocationState | null;
  const backgroundLocation = state?.backgroundLocation ?? location;

  return (
    <ToastProvider>
      <MarksProvider>
        <div
          className="min-h-dvh overflow-y-auto"
          style={{ paddingBottom: "calc(var(--nav-h) + env(safe-area-inset-bottom, 0px) + 12px)" }}
        >
          <Routes location={backgroundLocation}>
            <Route path="/" element={<Home />} />
            <Route path="/data" element={<Data />} />
            <Route path="/fav" element={<Fav />} />
            <Route path="/mine" element={<Mine />} />
            <Route path="/drill" element={<Drill />} />
            <Route path="/jobs/new" element={null} />
            <Route path="/jobs/:id" element={null} />
          </Routes>
        </div>
        <BottomTabBar />
        {location.pathname === "/jobs/new" && (
          <Routes>
            <Route path="/jobs/new" element={<ManualJobSheet />} />
          </Routes>
        )}
        {location.pathname.startsWith("/jobs/") && location.pathname !== "/jobs/new" && (
          <Routes>
            <Route path="/jobs/:id" element={<JobDetailSheet />} />
          </Routes>
        )}
      </MarksProvider>
    </ToastProvider>
  );
}
