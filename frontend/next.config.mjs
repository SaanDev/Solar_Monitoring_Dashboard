/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "api.helioviewer.org" },
      { protocol: "https", hostname: "sdo.gsfc.nasa.gov" },
      { protocol: "https", hostname: "soho.nascom.nasa.gov" },
    ],
  },
};

export default nextConfig;
