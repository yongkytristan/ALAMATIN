import type { NextConfig } from "next";

// The browser calls /api/* on this origin and Next proxies it to the address
// API, so the backend needs no CORS headers. That matters: src/alamatin/api.py
// is covered by the ALM-034 release freeze, and adding CORS there would mean
// re-freezing the release just to make a local run work.
const apiOrigin = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Development only. Without this, opening the app on 127.0.0.1 rather than
  // localhost makes Next block its own JS chunks: the page still renders from
  // the server, but never hydrates, so the character counter stays at 0 and the
  // submit button stays disabled with no error shown anywhere on screen.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiOrigin}/:path*` }];
  },
};

export default nextConfig;
