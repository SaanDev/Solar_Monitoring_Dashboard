import { DashboardShell } from "@/components/layout/DashboardShell";
import { ForecastClient } from "./ForecastClient";

export default function ForecastPage() {
  return (
    <DashboardShell title="Forecast & Prediction">
      <ForecastClient />
    </DashboardShell>
  );
}
