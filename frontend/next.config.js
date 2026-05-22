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
  env: {
    NEXT_PUBLIC_BASE_PATH: basePath,
    NEXT_PUBLIC_STATE_URL:
      process.env.NEXT_PUBLIC_STATE_URL ||
      "https://raw.githubusercontent.com/Architcybercrime/Stock-Market/main/data/paper_state.json",
  },
};

module.exports = nextConfig;
