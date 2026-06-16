import { DashboardShell } from "@/components/layout/DashboardShell";
import { SettingsClient } from "./SettingsClient";

export default function SettingsPage() {
  return (
    <DashboardShell title="Settings">
      <SettingsClient />
    </DashboardShell>
  );
}
