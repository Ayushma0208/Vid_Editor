"use client"

import { FormEvent, useMemo, useState } from "react"
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

export default function SignupPage() {
  const router = useRouter()
  const [firstName, setFirstName] = useState("")
  const [lastName, setLastName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const passwordStrength = useMemo(() => {
    let score = 0
    if (password.length >= 8) score += 1
    if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 1
    if (/[0-9]/.test(password)) score += 1
    if (/[^A-Za-z0-9]/.test(password)) score += 1
    return score
  }, [password])

  const strengthLabel = ["Weak", "Fair", "Good", "Strong"][Math.max(passwordStrength - 1, 0)]

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)

    if (password !== confirmPassword) {
      setError("Passwords do not match.")
      return
    }

    setIsSubmitting(true)
    try {
      const fullName = `${firstName} ${lastName}`.trim()
      const response = await api.post("/api/v1/auth/register", {
        email,
        password,
        full_name: fullName || null,
      })
      const accessToken = response.data?.access_token
      const refreshToken = response.data?.refresh_token

      if (!accessToken) throw new Error("Missing access token")
      localStorage.setItem("token", accessToken)
      if (refreshToken) localStorage.setItem("refresh_token", refreshToken)
      router.push("/dashboard")
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } })?.response?.status
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      if (status === 409) {
        setError(typeof detail === "string" ? detail : "This email is already registered. Please sign in instead.")
      } else if (typeof detail === "string" && detail.trim()) {
        setError(detail)
      } else {
        setError("Unable to create account. Please check your details.")
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className={`${dmSans.className} relative flex min-h-screen items-center justify-center overflow-hidden bg-[#faf8ff] px-4 text-[#191b23]`}>
      <div className="pointer-events-none absolute inset-0 opacity-40 [background:radial-gradient(circle_at_15%_50%,rgba(0,74,198,0.05)_0%,transparent_50%),radial-gradient(circle_at_85%_30%,rgba(113,42,226,0.05)_0%,transparent_50%)]" />

      <main className="relative z-10 w-full max-w-[420px]">
        <div className="mb-8 flex items-center justify-center">
          <div className="flex items-center gap-2">
            <span className="h-6 w-1.5 rounded-full bg-[#004ac6]" />
            <h1 className={`${syne.className} text-[34px] font-extrabold uppercase tracking-tight`}>Clip AI</h1>
          </div>
        </div>

        <div className="w-full rounded-xl border border-[#e1e2ed]/80 bg-white/85 p-8 shadow-[0_2px_10px_-3px_rgba(0,0,0,0.05),0_10px_20px_-5px_rgba(0,0,0,0.02),0_30px_60px_-15px_rgba(0,0,0,0.05)] backdrop-blur-xl">
          <div className="mb-6 text-center">
            <h2 className={`${syne.className} mb-1 text-[40px] font-extrabold leading-none tracking-tight`}>Create Account</h2>
            <p className="text-base text-[#434655]">Join the next generation editing workspace.</p>
          </div>

          <form className="space-y-6" onSubmit={onSubmit}>
            <div className="flex gap-4">
              <div className="flex-1 space-y-1">
                <label className={`${jetBrainsMono.className} block text-xs uppercase tracking-wider text-[#434655]`} htmlFor="firstName">
                  First Name
                </label>
                <input
                  id="firstName"
                  required
                  value={firstName}
                  onChange={(event) => setFirstName(event.target.value)}
                  className="h-9 w-full border-0 border-b border-[#c3c6d7] bg-transparent px-0 text-base outline-none transition-all focus:border-[#004ac6] focus:ring-0"
                  placeholder="Jane"
                />
              </div>
              <div className="flex-1 space-y-1">
                <label className={`${jetBrainsMono.className} block text-xs uppercase tracking-wider text-[#434655]`} htmlFor="lastName">
                  Last Name
                </label>
                <input
                  id="lastName"
                  required
                  value={lastName}
                  onChange={(event) => setLastName(event.target.value)}
                  className="h-9 w-full border-0 border-b border-[#c3c6d7] bg-transparent px-0 text-base outline-none transition-all focus:border-[#004ac6] focus:ring-0"
                  placeholder="Doe"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className={`${jetBrainsMono.className} block text-xs uppercase tracking-wider text-[#434655]`} htmlFor="email">
                Email Address
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="h-9 w-full border-0 border-b border-[#c3c6d7] bg-transparent px-0 text-base outline-none transition-all focus:border-[#004ac6] focus:ring-0"
                placeholder="jane@example.com"
              />
            </div>

            <div className="space-y-1">
              <label className={`${jetBrainsMono.className} block text-xs uppercase tracking-wider text-[#434655]`} htmlFor="password">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="h-9 w-full border-0 border-b border-[#c3c6d7] bg-transparent px-0 pr-10 text-base outline-none transition-all focus:border-[#004ac6] focus:ring-0"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  className="absolute right-0 top-1/2 -translate-y-1/2 text-sm text-[#434655]"
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
              <div className="mt-2 flex gap-1">
                {[0, 1, 2, 3].map((index) => (
                  <div key={index} className="h-1 flex-1 rounded-full bg-[#e1e2ed]">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: passwordStrength > index ? "100%" : "0%",
                        backgroundColor:
                          passwordStrength <= 1 ? "#ba1a1a" : passwordStrength <= 2 ? "#bc4800" : "#2563eb",
                      }}
                    />
                  </div>
                ))}
              </div>
              <span className="text-xs text-[#434655]">{strengthLabel} strength</span>
            </div>

            <div className="space-y-1">
              <label className={`${jetBrainsMono.className} block text-xs uppercase tracking-wider text-[#434655]`} htmlFor="confirmPassword">
                Confirm Password
              </label>
              <div className="relative">
                <input
                  id="confirmPassword"
                  type={showConfirmPassword ? "text" : "password"}
                  required
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  className="h-9 w-full border-0 border-b border-[#c3c6d7] bg-transparent px-0 pr-10 text-base outline-none transition-all focus:border-[#004ac6] focus:ring-0"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword((value) => !value)}
                  className="absolute right-0 top-1/2 -translate-y-1/2 text-sm text-[#434655]"
                >
                  {showConfirmPassword ? "Hide" : "Show"}
                </button>
              </div>
            </div>

            {error ? <p className="text-base text-red-600">{error}</p> : null}

            <button
              type="submit"
              disabled={isSubmitting}
              className="mt-4 h-12 w-full rounded-lg bg-gradient-to-r from-[#004ac6] to-[#712ae2] text-base font-medium text-white shadow-[0_4px_14px_0_rgba(0,74,198,0.25)] transition-all duration-200 hover:-translate-y-px hover:shadow-[0_6px_20px_rgba(0,74,198,0.3)] disabled:cursor-not-allowed disabled:opacity-70"
            >
              {isSubmitting ? "Creating account..." : "Create Account"}
            </button>
          </form>

          <div className="mt-8 border-t border-[#c3c6d7]/30 pt-4 text-center">
            <a className="text-base text-[#004ac6] transition-colors hover:text-[#0053db]" href="/login">
              Already have an account? <span className="font-medium">Sign In</span>
            </a>
          </div>
        </div>
      </main>
    </div>
  )
}
