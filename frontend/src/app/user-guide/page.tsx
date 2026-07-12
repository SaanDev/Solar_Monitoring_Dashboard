import { DashboardShell } from "@/components/layout/DashboardShell";
import { UserGuideClient } from "./UserGuideClient";

export default function UserGuidePage() {
  return (
    <DashboardShell title="User Guide">
      <UserGuideClient />
    </DashboardShell>
  );
}
