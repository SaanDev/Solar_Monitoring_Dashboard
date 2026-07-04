import { DashboardShell } from "@/components/layout/DashboardShell";
import { ReferenceClient } from "./ReferenceClient";

export default function ReferencePage() {
  return (
    <DashboardShell title="Science Reference">
      <ReferenceClient />
    </DashboardShell>
  );
}
