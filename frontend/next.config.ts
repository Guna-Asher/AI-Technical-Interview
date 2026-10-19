import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // No framework branding: hide the dev-mode badge and the X-Powered-By header.
  devIndicators: false,
  poweredByHeader: false,
};

export default nextConfig;
