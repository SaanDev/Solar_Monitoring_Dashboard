import { DashboardShell } from "@/components/layout/DashboardShell";
import { LascoPanel } from "@/components/coronagraph/LascoPanel";

export default function CoronagraphPage() {
  return (
    <DashboardShell title="SOHO/LASCO Coronagraph">
      <div className="space-y-4">
        <div className="rounded-lg border border-surface-border bg-surface-card p-4 text-xs text-slate-500">
          Latest LASCO C2 (1.5–6 R☉) and C3 (3.7–30 R☉) white-light coronagraph
          movies · source: SOHO/LASCO near-real-time · times in UTC
        </div>
        <div className="max-w-5xl rounded-lg border border-surface-border bg-surface-card p-4">
          <LascoPanel />
        </div>
      </div>
    </DashboardShell>
  );
}
