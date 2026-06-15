import { DashboardShell } from "@/components/layout/DashboardShell";
import { OverviewMetrics } from "./OverviewMetrics";
import { OverviewXrayChart } from "./OverviewXrayChart";
import { OverviewProtonChart } from "./OverviewProtonChart";
import { OverviewKpChart, OverviewDstChart } from "./OverviewGeomagnetic";
import { OverviewSolarImages } from "./OverviewSolarImages";
import { LascoPanel } from "@/components/coronagraph/LascoPanel";
import { SriLankaLivePanel } from "@/components/radio/SriLankaLivePanel";
import { BurstEventSlider } from "@/components/radio/BurstEventSlider";
import Link from "next/link";

const RADIO_HEIGHT = "h-[480px]";

export default function OverviewPage() {
  return (
    <DashboardShell title="Space Weather Overview">
      <div className="space-y-6">
        {/* Summary metric cards (live) — top */}
        <OverviewMetrics />

        {/* e-CALLISTO solar radio (Sri Lanka station) */}
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-xs uppercase tracking-widest text-slate-500">
              Solar Radio — e-CALLISTO
            </h2>
            <Link
              href="/solar-radio"
              className="text-xs text-accent-blue hover:underline"
            >
              Open full view →
            </Link>
          </div>
          {/* Split half/half: left = Sri Lanka live, right = burst events */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <SriLankaLivePanel heightClass={RADIO_HEIGHT} />
            <BurstEventSlider heightClass={RADIO_HEIGHT} />
          </div>
        </section>

        {/* X-ray chart (live) + proton placeholder */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <OverviewXrayChart />
          <OverviewProtonChart />
          <OverviewKpChart />
          <OverviewDstChart />
        </div>

        {/* Bottom row — Solar images + extended LASCO coronagraph movies */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <OverviewSolarImages />
          <div className="rounded-lg border border-surface-border bg-surface-card p-4 lg:col-span-2">
            <h3 className="mb-3 text-xs uppercase tracking-wider text-slate-500">
              LASCO Coronagraph — Latest Movies
            </h3>
            <LascoPanel />
          </div>
        </div>
      </div>
    </DashboardShell>
  );
}
