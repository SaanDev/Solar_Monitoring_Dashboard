import { DashboardShell } from "@/components/layout/DashboardShell";
import { BurstPredictorClient } from "./BurstPredictorClient";

export default function BurstPredictorPage() {
  return (
    <DashboardShell title="Burst Predictor">
      <BurstPredictorClient />
    </DashboardShell>
  );
}
