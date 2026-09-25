import { DashboardShell } from "@/components/layout/DashboardShell";
import { OverviewMetrics } from "./OverviewMetrics";
import { OverviewForecast } from "./OverviewForecast";
import { OverviewXrayChart } from "./OverviewXrayChart";
import { OverviewProtonChart } from "./OverviewProtonChart";
import { OverviewKpChart, OverviewDstChart } from "./OverviewGeomagnetic";
import { OverviewSolarImages } from "./OverviewSolarImages";
import { OverviewAlertsPanel } from "./OverviewAlertsPanel";
import { OverviewElectronChart } from "./OverviewElectronChart";
import { OverviewMagnetometerChart } from "./OverviewMagnetometerChart";
import { OverviewSolarWindChart, OverviewImfChart } from "./OverviewSolarWind";
import { OverviewSunspotChart } from "./OverviewSunspotChart";
import { OverviewRadioFlux } from "./OverviewRadioFlux";
import { LascoMovie } from "@/components/coronagraph/LascoPanel";
import { LiveRadioPanel } from "@/components/radio/LiveRadioPanel";

/**
 * Section divider for the Overview.
 *
 * ~20 panels previously ran together across 4–5 viewports, every one wearing the
 * same card and the same heading style, so nothing signalled where one topic
 * ended and the next began. These headings only group what already existed —
 * no panel internals are touched.
 */
function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="px-0.5 pt-2 text-[11px] font-semibold uppercase tracking-widest text-slate-500">
      {children}
    </h2>
  );
}

export default function OverviewPage() {
  return (
    <DashboardShell title="">
      <div className="space-y-4">
        {/* Row 1 — summary metric cards */}
        <OverviewMetrics />

        {/* Row 1.5 — forecast strip: predicted Kp, inbound CMEs, 3-day outlook */}
        <OverviewForecast />

        <SectionHeading>Solar activity</SectionHeading>

        {/* Row 2 — radio dynamic spectrum + GOES X-ray + GOES proton */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-12">
          <div className="flex flex-col lg:col-span-5">
            <LiveRadioPanel heightClass="flex-1 min-h-[18rem]" />
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

          {/* Relative wrapper + absolute panel (on lg) so the feed fills — but
              never exceeds — the height of the left column, scrolling internally. */}
          <div className="lg:relative lg:col-span-3">
            <OverviewAlertsPanel className="h-full lg:absolute lg:inset-0" limit={5} />
          </div>
        </div>

        <SectionHeading>Geospace &amp; near-Earth</SectionHeading>

        {/* Row 5 — solar wind speed + IMF Bt/Bz (real-time L1) */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <OverviewSolarWindChart />
          <OverviewImfChart />
        </div>

        {/* Row 6 — GOES electron flux + magnetometer (real-time) */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <OverviewElectronChart />
          <OverviewMagnetometerChart />
        </div>

        <SectionHeading>Long-term indices</SectionHeading>

        {/* Row 7 — F10.7 radio flux (bottom-left) + sunspot progression */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
          <div className="flex flex-col lg:col-span-4">
            <OverviewRadioFlux />
          </div>
          <div className="flex flex-col lg:col-span-8">
            <OverviewSunspotChart />
          </div>
        </div>
      </div>
    </DashboardShell>
  );
}
