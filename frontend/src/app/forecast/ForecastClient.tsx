"use client";

import { KpForecastPanel } from "@/components/forecast/KpForecastPanel";
import { CmeList } from "@/components/forecast/CmeList";
import { CmeHistogram } from "@/components/forecast/CmeHistogram";
import { PastCmeList } from "@/components/forecast/PastCmeList";
import { NoaaScalesPanel } from "@/components/forecast/NoaaScalesPanel";
import { AuroraPanel } from "@/components/forecast/AuroraPanel";

export function ForecastClient() {
  return (
    <div className="space-y-4">
      {/* Row 1 — predicted Kp (local Newell coupling) + NOAA's official outlook */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-7">
          <KpForecastPanel />
        </div>
        <div className="lg:col-span-5">
          <NoaaScalesPanel />
        </div>
      </div>

      {/* Row 2 — DONKI CME catalog: upcoming/inbound, eruption-cadence
          histogram, then a past-window log */}
      <CmeList days={7} />
      <CmeHistogram />
      <PastCmeList />

      {/* Row 3 — OVATION aurora oval */}
      <AuroraPanel />
    </div>
  );
}
