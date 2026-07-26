import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "@/styles/globals.css";
import { AppProvider } from "@/components/providers";
import { Sidebar } from "@/components/layout/Sidebar";

// Both families were already named in globals.css / tailwind.config.ts but were
// never actually loaded, so every numeric readout fell back to the OS default
// monospace. next/font self-hosts them, so there's no network request or FOUT.
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-jetbrains-mono",
});

export const metadata: Metadata = {
  title: "Space Weather Dashboard",
  description: "Real-time space weather monitoring and analysis",
};

// Apply the persisted theme before paint to avoid a flash of the wrong theme.
const themeScript = `(function(){try{var t=localStorage.getItem('theme')||'dark';var d=t==='dark'||(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);}catch(e){document.documentElement.classList.add('dark');}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`dark ${inter.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="flex h-screen overflow-hidden bg-surface text-slate-200 antialiased">
        {/* Skip link — the sidebar puts 18 nav links ahead of the content, so
            keyboard users had no way past them. Visually hidden until focused. */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-accent-blue focus:px-3 focus:py-2 focus:text-xs focus:font-medium focus:text-white"
        >
          Skip to main content
        </a>
        <AppProvider>
          <Sidebar />
          {children}
        </AppProvider>
      </body>
    </html>
  );
}
