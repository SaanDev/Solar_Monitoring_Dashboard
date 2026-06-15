import type { Metadata } from "next";
import "@/styles/globals.css";
import { Sidebar } from "@/components/layout/Sidebar";

export const metadata: Metadata = {
  title: "Space Weather Dashboard",
  description: "Real-time space weather monitoring and analysis",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="flex h-screen overflow-hidden bg-surface text-slate-200 antialiased">
        <Sidebar />
        {children}
      </body>
    </html>
  );
}
