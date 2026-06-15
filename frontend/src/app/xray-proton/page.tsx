import { DashboardShell } from "@/components/layout/DashboardShell";
import { XrayProtonClient } from "./XrayProtonClient";

export default function XrayProtonPage() {
  return (
    <DashboardShell title="X-ray & Proton Flux">
      <XrayProtonClient />
    </DashboardShell>
  );
}
