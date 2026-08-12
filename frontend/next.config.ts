import type { NextConfig } from "next"
import { dirname } from "path"
import { fileURLToPath } from "url"

const frontendRoot = dirname(fileURLToPath(import.meta.url))

const nextConfig: NextConfig = {
  output: "standalone",
  // Keep these identical so Next doesn't warn in CI / Vercel builds.
  outputFileTracingRoot: frontendRoot,
  turbopack: {
    root: frontendRoot,
  },
}

export default nextConfig
