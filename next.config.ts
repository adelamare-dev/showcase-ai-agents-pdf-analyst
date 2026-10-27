import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the root to this app: otherwise Turbopack picks the topmost lockfile
  // or pnpm-workspace.yaml it finds (e.g. a parent monorepo) and fails to
  // resolve this app's node_modules.
  turbopack: { root: __dirname },
};

export default nextConfig;
