import { DashboardShell } from "@/components/layout/DashboardShell";
import { SolarWindClient } from "./SolarWindClient";

export default function SolarWindPage() {
  return (
    <DashboardShell title="Solar Wind & IMF">
      <SolarWindClient />
    </DashboardShell>
  );
}
