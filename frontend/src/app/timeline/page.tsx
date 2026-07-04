import { DashboardShell } from "@/components/layout/DashboardShell";
import { TimelineClient } from "./TimelineClient";

export default function TimelinePage() {
  return (
    <DashboardShell title="Event Timeline">
      <TimelineClient />
    </DashboardShell>
  );
}
