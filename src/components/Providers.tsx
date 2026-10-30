"use client";

import { CopilotKit } from "@copilotkit/react-core/v2";
import { createMirrorActivityRenderer } from "@/a2ui/MirrorRenderer";

/* Both agents send A2UI surfaces via activity messages. We intercept those
 * with our mirror renderer and forward them to the page-level SurfaceCanvas,
 * so the dashboard renders at full canvas size instead of as a chat bubble.
 *
 * The pill the renderer leaves behind in chat is the user-visible breadcrumb
 * ("surface → rendered in the canvas"). */
const RENDERERS = [
  createMirrorActivityRenderer("fixed_agent"),
  createMirrorActivityRenderer("dynamic_agent"),
];

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    /* enableInspector={false}: the dev Inspector auto-mounts on localhost and
     * issues GET {runtimeUrl}/threads?agentId=<id> for every declared agent on
     * each mount / reload / HMR reconnect. single-route mode only serves the
     * POST envelope, so those calls are structural 404s, re-logged as a burst
     * on every page load (see SETUP/2026-10-27-orchestration-loop/AUDIT.md). */
    /* useSingleEndpoint: the default "auto" transport probes GET {runtimeUrl}/info
     * first, which a single-route runtime answers with a 404 (one console error
     * per page load) before falling back to the POST envelope. The route is
     * single-route only, so say so and skip the probe. */
    <CopilotKit
      runtimeUrl="/api/copilotkit"
      useSingleEndpoint
      renderActivityMessages={RENDERERS}
      enableInspector={false}
    >
      {children}
    </CopilotKit>
  );
}
