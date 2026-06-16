import type { Metadata } from "next";
import "@/styles/globals.css";
import { AppProvider } from "@/components/providers";
import { Sidebar } from "@/components/layout/Sidebar";

export const metadata: Metadata = {
  title: "Space Weather Dashboard",
  description: "Real-time space weather monitoring and analysis",
};

// Apply the persisted theme before paint to avoid a flash of the wrong theme.
const themeScript = `(function(){try{var t=localStorage.getItem('theme')||'dark';var d=t==='dark'||(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);}catch(e){document.documentElement.classList.add('dark');}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="flex h-screen overflow-hidden bg-surface text-slate-200 antialiased">
        <AppProvider>
          <Sidebar />
          {children}
        </AppProvider>
      </body>
    </html>
  );
}
