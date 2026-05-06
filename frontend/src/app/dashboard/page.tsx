"use client"

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import api from "@/lib/api"

type ProjectItem = {
  id?: string
  _id?: string
  title?: string
  status?: string
  thumbnail_url?: string | null
  duration_seconds?: number | null
  created_at?: string
}

function formatDuration(totalSeconds?: number | null) {
  if (!totalSeconds || totalSeconds < 1) return "--:--"
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = Math.floor(totalSeconds % 60)
  if (hours > 0) return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`
}

function statusBadge(status: string) {
  const s = status.toLowerCase()
  if (s === "ready") return { label: "Ready", className: "bg-emerald-100 text-emerald-700" }
  if (s === "downloading") return { label: "Downloading…", className: "bg-blue-100 text-blue-700 animate-pulse" }
  if (s === "error") return { label: "Error", className: "bg-red-100 text-red-700" }
  return { label: "Pending", className: "bg-amber-100 text-amber-700" }
}

export default function DashboardPage() {
  const router = useRouter()
  const [projects, setProjects] = useState<ProjectItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [ytUrl, setYtUrl] = useState("")
  const [isCreating, setIsCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState<Set<string>>(new Set())

  const loadProjects = useCallback(async () => {
    try {
      const response = await api.get("/api/v1/projects/")
      setProjects(Array.isArray(response.data) ? response.data : [])
    } catch {
      /* keep existing list on background poll failure */
    }
  }, [])

  useEffect(() => {
    const token = localStorage.getItem("token")
    if (!token) {
      router.push("/login")
      return
    }
    api
      .get("/api/v1/projects/")
      .then((response) => {
        setProjects(Array.isArray(response.data) ? response.data : [])
      })
      .catch(() => {
        setError("Could not load projects.")
      })
      .finally(() => {
        setIsLoading(false)
      })
  }, [router])

  // Auto-refresh every 10s when any project is downloading/pending
  useEffect(() => {
    const hasInProgress = projects.some((p) => {
      const s = (p.status || "").toLowerCase()
      return s === "downloading" || s === "pending"
    })
    if (!hasInProgress) return
    const interval = setInterval(loadProjects, 10000)
    return () => clearInterval(interval)
  }, [projects, loadProjects])

  const stats = useMemo(() => {
    const totalProjects = projects.length
    const downloading = projects.filter((project) => (project.status || "").toLowerCase() === "downloading").length
    const ready = projects.filter((project) => (project.status || "").toLowerCase() === "ready").length
    return { totalProjects, downloading, ready }
  }, [projects])

  const handleCreateProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!ytUrl.trim()) return
    setIsCreating(true)
    setError(null)
    try {
      await api.post("/api/v1/projects/", { yt_url: ytUrl.trim() })
      setYtUrl("")
      setIsModalOpen(false)
      await loadProjects()
    } catch {
      setError("Could not create project. Make sure the YouTube URL is valid.")
    } finally {
      setIsCreating(false)
    }
  }

  const handleRetryDownload = async (e: React.MouseEvent, projectId: string) => {
    e.stopPropagation()
    setRetrying((prev) => new Set(prev).add(projectId))
    try {
      await api.post(`/api/v1/projects/${projectId}/retry-download`)
      await loadProjects()
    } catch {
      setError("Retry failed. Please try again.")
    } finally {
      setRetrying((prev) => {
        const next = new Set(prev)
        next.delete(projectId)
        return next
      })
    }
  }

  const handleCardClick = (project: ProjectItem) => {
    const id = project.id || project._id
    if (!id) return
    router.push(`/project/${id}/clips`)
  }

  return (
    <div className="min-h-screen bg-[#faf8ff] text-[#191b23]">
      <header className="sticky top-0 z-40 flex h-12 items-center justify-between border-b border-[#e1e2ed] bg-white/70 px-4 shadow-[0_2px_10px_-3px_rgba(0,0,0,0.07)] backdrop-blur-xl">
        <div className="flex items-center gap-6">
          <span className="text-xl font-black tracking-tight">Clip AI</span>
          <nav className="hidden gap-4 md:flex">
            <span className="text-sm font-bold text-[#004ac6]">Project</span>
            <span className="text-sm font-bold text-[#737686]">Edit</span>
            <span className="text-sm font-bold text-[#737686]">View</span>
            <span className="text-sm font-bold text-[#737686]">Export</span>
          </nav>
        </div>
        <button
          onClick={() => {
            localStorage.removeItem("token")
            localStorage.removeItem("refresh_token")
            router.push("/login")
          }}
          className="rounded-lg border border-[#c3c6d7] px-3 py-1 text-xs font-medium hover:bg-[#f3f3fe]"
        >
          Logout
        </button>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">Dashboard Home</h1>
            <p className="text-sm text-[#434655]">Manage your projects and import new videos.</p>
          </div>
          <button
            onClick={() => setIsModalOpen(true)}
            className="rounded-lg bg-gradient-to-r from-[#004ac6] to-[#712ae2] px-5 py-2 text-sm font-medium text-white shadow-[0_4px_14px_0_rgba(0,74,198,0.39)] hover:opacity-90"
          >
            New Project
          </button>
        </div>

        <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="rounded-xl border border-[#e1e2ed] bg-white p-4">
            <p className="text-sm text-[#434655]">Total Projects</p>
            <p className="text-3xl font-extrabold">{stats.totalProjects}</p>
          </div>
          <div className="rounded-xl border border-[#e1e2ed] bg-white p-4">
            <p className="text-sm text-[#434655]">Downloading</p>
            <p className="text-3xl font-extrabold">{stats.downloading}</p>
          </div>
          <div className="rounded-xl border border-[#e1e2ed] bg-white p-4">
            <p className="text-sm text-[#434655]">Ready</p>
            <p className="text-3xl font-extrabold">{stats.ready}</p>
          </div>
        </div>

        {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}

        {isLoading ? (
          <p className="text-sm text-[#434655]">Loading projects...</p>
        ) : projects.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[#c3c6d7] bg-white p-8 text-center text-sm text-[#434655]">
            No projects yet. Click <span className="font-semibold">New Project</span> to import a YouTube URL.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
            {projects.map((project) => {
              const id = project.id || project._id || ""
              const st = (project.status || "pending").toLowerCase()
              const badge = statusBadge(st)
              const isRetryable = st === "pending" || st === "error"
              const isRetryingThis = retrying.has(id)

              return (
                <article
                  key={id || project.title}
                  onClick={() => handleCardClick(project)}
                  className="cursor-pointer rounded-xl border border-[#e1e2ed] bg-white p-3 shadow-sm transition-all hover:border-[#004ac6]/40 hover:shadow-md"
                >
                  <div className="relative mb-3 aspect-video overflow-hidden rounded-lg bg-[#ededf9]">
                    {project.thumbnail_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={project.thumbnail_url} alt={project.title || "Project"} className="h-full w-full object-cover" />
                    ) : (
                      <div className="flex h-full items-center justify-center text-sm text-[#737686]">No thumbnail</div>
                    )}
                    <div className="absolute bottom-2 right-2 rounded bg-black/70 px-2 py-0.5 text-[11px] text-white">
                      {formatDuration(project.duration_seconds)}
                    </div>
                  </div>
                  <h3 className="line-clamp-2 text-sm font-medium">{project.title || "Untitled Project"}</h3>
                  <div className="mt-2 flex items-center justify-between">
                    <span className={`inline-block rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${badge.className}`}>
                      {badge.label}
                    </span>
                    {isRetryable && (
                      <button
                        onClick={(e) => handleRetryDownload(e, id)}
                        disabled={isRetryingThis}
                        className="rounded-md bg-[#004ac6] px-3 py-1 text-[11px] font-medium text-white hover:bg-[#0053db] disabled:opacity-50"
                      >
                        {isRetryingThis ? "Retrying…" : "Retry Download"}
                      </button>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </main>

      {isModalOpen ? (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/20 p-4 backdrop-blur-sm">
          <div className="w-full max-w-[480px] overflow-hidden rounded-xl border border-[#e1e2ed] bg-white/75 shadow-[0_2px_4px_-1px_rgba(0,0,0,0.03),0_10px_15px_-3px_rgba(0,0,0,0.05),0_30px_60px_-10px_rgba(0,0,0,0.15)] backdrop-blur-2xl">
            <div className="flex items-center justify-between border-b border-[#e1e2ed] bg-[#faf8ff]/70 px-6 py-4">
              <h2 className="text-lg font-bold">Import from YouTube</h2>
              <button onClick={() => setIsModalOpen(false)} className="rounded p-1 text-[#737686] hover:bg-[#ededf9] hover:text-[#191b23]">
                Close
              </button>
            </div>
            <form onSubmit={handleCreateProject} className="space-y-6 p-6">
              <div>
                <label className="mb-2 block text-[10px] uppercase text-[#737686]">YouTube URL</label>
                <div className="flex items-center">
                  <input
                    value={ytUrl}
                    onChange={(event) => setYtUrl(event.target.value)}
                    placeholder="https://youtube.com/watch?v=..."
                    className="w-full border-0 border-b border-[#c3c6d7] bg-transparent py-2 text-sm outline-none transition-colors focus:border-[#004ac6]"
                    required
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 border-t border-[#e1e2ed] pt-4">
                <button type="button" onClick={() => setIsModalOpen(false)} className="px-4 py-2 text-sm text-[#434655] hover:text-[#191b23]">
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreating}
                  className="rounded-lg bg-[#004ac6] px-5 py-2 text-sm font-medium text-white shadow-sm hover:bg-[#0053db] disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {isCreating ? "Importing..." : "Import Media"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  )
}
