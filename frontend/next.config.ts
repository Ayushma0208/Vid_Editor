import type { NextConfig } from "next"
import { dirname } from "path"
import { fileURLToPath } from "url"

const frontendRoot = dirname(fileURLToPath(import.meta.url))

const nextConfig: NextConfig = {
  output: "standalone",
  turbopack: {
    root: frontendRoot,
  },
}

export default nextConfig
