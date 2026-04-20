import type { NextConfig } from "next";

const config: NextConfig = {
  // Next.js 16: cacheComponents moved out of `experimental`. No custom server.
  // All FastAPI traffic flows through Next.js Route Handlers and Server Components
  // that inject the bearer token server-side.
  cacheComponents: true,
  reactStrictMode: true,
  typescript: {
    ignoreBuildErrors: false,
  },
};

export default config;
