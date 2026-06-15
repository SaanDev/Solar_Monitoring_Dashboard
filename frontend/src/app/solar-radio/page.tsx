import { DashboardShell } from "@/components/layout/DashboardShell";
import { SriLankaLivePanel } from "@/components/radio/SriLankaLivePanel";
import { BurstEventSlider } from "@/components/radio/BurstEventSlider";

export default function SolarRadioPage() {
  return (
    <DashboardShell title="e-CALLISTO Solar Radio">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Left — live Sri Lanka data */}
        <section className="flex flex-col">
          <h1 className="mb-2 text-xs uppercase tracking-widest text-slate-500">
            Live Data — Sri Lanka
          </h1>
          <SriLankaLivePanel />
        </section>

        {/* Right — burst events */}
        <section className="flex flex-col">
          <h1 className="mb-2 text-xs uppercase tracking-widest text-slate-500">
            Burst Events
          </h1>
          <BurstEventSlider />
        </section>
      </div>
    </DashboardShell>
  );
}
