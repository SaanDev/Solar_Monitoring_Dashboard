import { DashboardShell } from "@/components/layout/DashboardShell";
import { ECallistoAnalyzerClient } from "./ECallistoAnalyzerClient";

export default function ECallistoAnalyzerPage() {
  return (
    <DashboardShell title="e-CALLISTO Analyzer">
      <ECallistoAnalyzerClient />
    </DashboardShell>
  );
}
