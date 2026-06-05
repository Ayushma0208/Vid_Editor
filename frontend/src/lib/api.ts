import axios from "axios"

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = typeof window !== "undefined"
    ? localStorage.getItem("token")
    : null
  if (token) config.headers.Authorization = `Bearer ${token}`
  if (config.data instanceof FormData) {
    delete config.headers["Content-Type"]
  }
  return config
})

export default api
