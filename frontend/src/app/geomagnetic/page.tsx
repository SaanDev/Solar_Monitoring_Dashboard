import { DashboardShell } from "@/components/layout/DashboardShell";
import { GeomagneticClient } from "./GeomagneticClient";

export default function GeomagneticPage() {
  return (
    <DashboardShell title="Geomagnetic Indices">
      <GeomagneticClient />
    </DashboardShell>
  );
}
