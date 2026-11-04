import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

/** Static export for production; in `next dev`, proxy /api to the FastAPI backend. */
export default function config(phase: string): NextConfig {
  const base: NextConfig = {
    turbopack: {
      rules: {
        "*.css": {
          loaders: ["@tailwindcss/turbopack"],
          as: "*.css",
        },
      },
    },
  };

  if (phase === PHASE_DEVELOPMENT_SERVER) {
    return {
      ...base,
      compress: false,
      devIndicators: false,
      rewrites: async () => [
        { source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` },
      ],
    };
  }

  return { ...base, output: "export", images: { unoptimized: true } };
}
