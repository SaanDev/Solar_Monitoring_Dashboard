import { DashboardShell } from "@/components/layout/DashboardShell";
import { OverviewMetrics } from "./OverviewMetrics";
import { OverviewXrayChart } from "./OverviewXrayChart";
import { OverviewProtonChart } from "./OverviewProtonChart";
import { OverviewKpChart, OverviewDstChart } from "./OverviewGeomagnetic";
import { OverviewSolarImages } from "./OverviewSolarImages";
import { OverviewAlertsPanel } from "./OverviewAlertsPanel";
import { LascoMovie } from "@/components/coronagraph/LascoPanel";
import { SriLankaLivePanel } from "@/components/radio/SriLankaLivePanel";

export default function OverviewPage() {
  return (
    <DashboardShell title="">
      <div className="space-y-4">
        {/* Row 1 — summary metric cards */}
        <OverviewMetrics />

        {/* Row 2 — radio dynamic spectrum + GOES X-ray + GOES proton */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
          <div className="flex flex-col lg:col-span-5">
            <SriLankaLivePanel heightClass="flex-1 min-h-[18rem]" />
          </div>
          <div className="flex flex-col lg:col-span-4">
            <OverviewXrayChart />
          </div>
          <div className="flex flex-col lg:col-span-3">
            <OverviewProtonChart />
          </div>
        </div>

        {/* Rows 3–4 — geomagnetic + LASCO movie + SDO strip (left), tall alerts feed (right) */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
          <div className="space-y-4 lg:col-span-9">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <OverviewDstChart />
              <OverviewKpChart />
              <div className="flex h-full min-h-[16rem] flex-col rounded-lg border border-surface-border bg-surface-card p-4">
                <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
                  SOHO/LASCO C2 — Short Movie
                </h3>
                <div className="flex-1">
                  <LascoMovie camera="C2" />
                </div>
              </div>
            </div>
            <OverviewSolarImages />
          </div>

          <div className="lg:col-span-3">
            <OverviewAlertsPanel className="h-full" />
          </div>
        </div>
      </div>
    </DashboardShell>
  );
}
