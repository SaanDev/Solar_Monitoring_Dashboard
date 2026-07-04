import { DashboardShell } from "@/components/layout/DashboardShell";
import { SolarCycleClient } from "./SolarCycleClient";

export default function SolarCyclePage() {
  return (
    <DashboardShell title="Solar Cycle Progression">
      <SolarCycleClient />
    </DashboardShell>
  );
}
