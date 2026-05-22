/** @type {import('next').NextConfig} */
// Static export config for GitHub Pages deployment.
// The dashboard fetches paper_state.json from raw.githubusercontent.com so
// it works as a fully static site with no server.
//
// For GitHub Pages under /Stock-Market/, set BASE_PATH=/Stock-Market at build
// time. For a custom domain or root deploy, leave it empty.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig = {
  output: "export",
  reactStrictMode: true,
  trailingSlash: true,
  basePath,
  images: { unoptimized: true },
  // Don't fail the build for lint issues — we lint in a separate CI step.
  // The deploy workflow's job is to ship the dashboard, not enforce style.
  eslint: { ignoreDuringBuilds: true },
  // Same for TS — but we still typecheck via `npm run typecheck` in CI.
  // The dashboard build should not fail on a stray type complaint.
  typescript: { ignoreBuildErrors: true },
  env: {
    NEXT_PUBLIC_BASE_PATH: basePath,
    NEXT_PUBLIC_STATE_URL:
      process.env.NEXT_PUBLIC_STATE_URL ||
      "https://raw.githubusercontent.com/Architcybercrime/Stock-Market/main/data/paper_state.json",
  },
};

module.exports = nextConfig;
