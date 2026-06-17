import { DashboardShell } from "@/components/layout/DashboardShell";
import { EventsClient } from "./EventsClient";

export default function EventsPage() {
  return (
    <DashboardShell title="Events">
      <EventsClient />
    </DashboardShell>
  );
}
