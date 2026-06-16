import { DashboardShell } from "@/components/layout/DashboardShell";
import { ArchiveClient } from "./ArchiveClient";

export default function ArchivePage() {
  return (
    <DashboardShell title="Archive">
      <ArchiveClient />
    </DashboardShell>
  );
}
