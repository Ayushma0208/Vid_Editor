import axios from "axios"

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || ""
const PUBLIC_AUTH_PATHS = ["/api/v1/auth/login", "/api/v1/auth/register"]

const api = axios.create({
  baseURL: apiBaseUrl,
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const url = `${config.baseURL ?? ""}${config.url ?? ""}`
  const isPublicAuth = PUBLIC_AUTH_PATHS.some((path) => url.includes(path))
  if (!isPublicAuth) {
    const token = typeof window !== "undefined"
      ? localStorage.getItem("token")
      : null
    if (token) config.headers.Authorization = `Bearer ${token}`
  }
  if (config.data instanceof FormData) {
    delete config.headers["Content-Type"]
  }
  return config
})

export function isTransientNetworkError(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false
  if (!error.response) return true
  return [502, 503, 504].includes(error.response.status)
}

export async function withTransientRetry<T>(request: () => Promise<T>, retries = 1): Promise<T> {
  try {
    return await request()
  } catch (error) {
    if (retries > 0 && isTransientNetworkError(error)) {
      await new Promise((resolve) => setTimeout(resolve, 2500))
      return withTransientRetry(request, retries - 1)
    }
    throw error
  }
}

export async function wakeApiServer(timeoutMs = 90000): Promise<boolean> {
  if (!apiBaseUrl || typeof window === "undefined") return false
  const health = `${apiBaseUrl.replace(/\/$/, "")}/health`
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const response = await fetch(health, { cache: "no-store", mode: "cors" })
      if (response.ok) return true
    } catch {
      // Render free instances often 502 while booting.
    }
    await new Promise((resolve) => setTimeout(resolve, 3000))
  }
  return false
}

export default api
