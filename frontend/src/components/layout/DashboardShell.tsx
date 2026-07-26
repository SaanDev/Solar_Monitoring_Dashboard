import { Header } from "./Header";
import { Footer } from "./Footer";

export function DashboardShell({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <Header title={title} />
      {/* id is the skip-link target (see app/layout.tsx). Padding tightens on
          small screens, where 24px on each side is a meaningful share of a
          375px viewport. */}
      <main id="main-content" className="flex-1 overflow-y-auto p-4 sm:p-6">
        {children}
      </main>
      <Footer />
    </div>
  );
}
