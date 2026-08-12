import type { NextConfig } from "next"
import { dirname } from "path"
import { fileURLToPath } from "url"

const frontendRoot = dirname(fileURLToPath(import.meta.url))
const isVercel = Boolean(process.env.VERCEL)

const nextConfig: NextConfig = {
  // Standalone is for Docker/self-host only. On Vercel it breaks deploy output.
  ...(!isVercel ? { output: "standalone" as const } : {}),
  // Local/Docker monorepo roots; leave unset on Vercel to avoid path mismatches.
  ...(!isVercel
    ? {
        outputFileTracingRoot: frontendRoot,
        turbopack: {
          root: frontendRoot,
        },
      }
    : {}),
}

export default nextConfig
