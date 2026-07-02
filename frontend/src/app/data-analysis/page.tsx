import { DashboardShell } from "@/components/layout/DashboardShell";
import { DataAnalysisClient } from "./DataAnalysisClient";

export default function DataAnalysisPage() {
  return (
    <DashboardShell title="Data Analysis">
      <DataAnalysisClient />
    </DashboardShell>
  );
}
