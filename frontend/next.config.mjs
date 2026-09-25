// `npm run build:desktop` sets NEXT_OUTPUT=export: a fully static build in out/
// that the Windows desktop app's backend serves itself (see docs/desktop.md).
// Every page fetches its data client-side, so nothing needs a Node server.
// trailingSlash makes each route a directory index (archive/index.html), which
// is what the backend's static file server resolves. The website build is
// unaffected when NEXT_OUTPUT is unset.
const desktopExport = process.env.NEXT_OUTPUT === "export";

/** @type {import('next').NextConfig} */
const nextConfig = {
  ...(desktopExport && { output: "export", trailingSlash: true }),
  images: {
    ...(desktopExport && { unoptimized: true }),
    remotePatterns: [
      { protocol: "https", hostname: "api.helioviewer.org" },
      { protocol: "https", hostname: "sdo.gsfc.nasa.gov" },
      { protocol: "https", hostname: "soho.nascom.nasa.gov" },
    ],
  },
};

export default nextConfig;
