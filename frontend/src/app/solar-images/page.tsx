import { DashboardShell } from "@/components/layout/DashboardShell";
import { SolarImagesClient } from "./SolarImagesClient";

export default function SolarImagesPage() {
  return (
    <DashboardShell title="Solar Images">
      <SolarImagesClient />
    </DashboardShell>
  );
}
