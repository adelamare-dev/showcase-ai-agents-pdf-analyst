import type { NextConfig } from "next";

// Model output is rendered as markdown, and a prompt-injected document could
// make the model emit an image whose URL carries data to a third party. The
// browser therefore loads images and media from this origin only. Scripts,
// styles, fetches and workers are left unrestricted: `next dev` needs eval and
// its HMR websocket, and the pdf.js worker is bundled as a local asset.
const CONTENT_SECURITY_POLICY = [
  "img-src 'self' data: blob:",
  "media-src 'self'",
  "object-src 'none'",
  "frame-src 'none'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const nextConfig: NextConfig = {
  // AGENTS.md is maintained by hand: `next dev` must not append its own rules.
  agentRules: false,
  // Pin the root to this app: otherwise Turbopack picks the topmost lockfile
  // or pnpm-workspace.yaml it finds (e.g. a parent monorepo) and fails to
  // resolve this app's node_modules.
  turbopack: { root: __dirname },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: CONTENT_SECURITY_POLICY },
        ],
      },
    ];
  },
};

export default nextConfig;
