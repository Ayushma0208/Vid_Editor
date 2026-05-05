"use client"

import { FormEvent, useState } from "react"
import { useRouter } from "next/navigation"
import { DM_Sans, JetBrains_Mono, Syne } from "next/font/google"
import api from "@/lib/api"

const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
})

const syne = Syne({
  subsets: ["latin"],
  weight: ["700", "800"],
})

const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["500", "600"],
})

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      const response = await api.post("/api/v1/auth/login", {
        email,
        password,
      })
      const accessToken = response.data?.access_token
      const refreshToken = response.data?.refresh_token

      if (!accessToken) {
        throw new Error("Missing access token in response")
      }

      localStorage.setItem("token", accessToken)
      if (refreshToken) localStorage.setItem("refresh_token", refreshToken)
      router.push("/dashboard")
    } catch {
      setError("Invalid email or password. Please try again.")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className={`${dmSans.className} relative flex min-h-screen items-center justify-center overflow-hidden bg-[#faf8ff] px-4 text-[#191b23]`}>
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-cover bg-center opacity-10"
        style={{
          backgroundImage:
            "url('https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=2564&auto=format&fit=crop')",
        }}
      />

      <main className="relative z-10 w-full max-w-[420px] rounded-xl border border-[#c3c6d7] bg-white p-10 shadow-[0_30px_60px_-15px_rgba(0,0,0,0.1),0_10px_10px_-5px_rgba(0,0,0,0.04)]">
        <div className="mb-8 flex flex-col items-center">
          <div className="mb-2 flex items-center gap-2">
            <div className="h-6 w-1 bg-[#2563eb]" />
            <h1 className={`${syne.className} m-0 text-4xl font-extrabold tracking-tight`}>
              CLIP<span className="text-[#2563eb]">AI</span>
            </h1>
          </div>
          <p className="m-0 text-sm text-[#434655]">Professional video editing, simplified.</p>
        </div>

        <form className="space-y-6" onSubmit={onSubmit}>
          <div className="space-y-1">
            <label className={`${jetBrainsMono.className} text-xs uppercase tracking-wide text-[#434655]`} htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              placeholder="name@company.com"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="h-11 w-full rounded-lg border border-[#c3c6d7] bg-transparent px-3 text-sm text-[#191b23] transition-all focus:border-[#2563eb] focus:outline-none focus:ring-2 focus:ring-[#2563eb]/20"
            />
          </div>

          <div className="space-y-1">
            <label className={`flex justify-between text-xs uppercase tracking-wide text-[#434655] ${jetBrainsMono.className}`} htmlFor="password">
              <span>Password</span>
              <a className="normal-case text-[#2563eb] hover:underline" href="#">
                Forgot?
              </a>
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="h-11 w-full rounded-lg border border-[#c3c6d7] bg-transparent px-3 pr-11 text-sm text-[#191b23] transition-all focus:border-[#2563eb] focus:outline-none focus:ring-2 focus:ring-[#2563eb]/20"
              />
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
                className="absolute inset-y-0 right-0 px-3 text-[#737686] transition-colors hover:text-[#191b23]"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </div>

          {error ? <p className="text-sm text-red-600">{error}</p> : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#2563eb] text-sm font-medium text-white transition-all duration-150 hover:-translate-y-px hover:shadow-md disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isSubmitting ? "Signing in..." : "Sign In"}
          </button>
        </form>

        <div className="mt-8 text-center">
          <p className="m-0 text-sm text-[#434655]">
            Don&apos;t have an account?{" "}
            <a className="font-medium text-[#2563eb] hover:underline" href="/signup">
              Register
            </a>
          </p>
        </div>
      </main>
    </div>
  )
}
