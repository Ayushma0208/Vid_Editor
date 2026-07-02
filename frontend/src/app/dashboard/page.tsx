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
  metadata?: Record<string, unknown> | null
}

function formatDuration(totalSeconds?: number | null) {
  if (!totalSeconds || totalSeconds < 1) return "--:--"
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = Math.floor(totalSeconds % 60)
  if (hours > 0)
    return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`
}

function statusBadge(status: string) {
  const s = status.toLowerCase()
  if (s === "ready") return { label: "Ready", dot: "#10b981", className: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" }
  if (s === "downloading") return { label: "Downloading…", dot: "#3b82f6", className: "bg-blue-500/10 text-blue-400 border border-blue-500/20 animate-pulse" }
  if (s === "error") return { label: "Error", dot: "#ef4444", className: "bg-red-500/10 text-red-400 border border-red-500/20" }
  if (s === "processing") return { label: "Processing…", dot: "#a855f7", className: "bg-purple-500/10 text-purple-400 border border-purple-500/20 animate-pulse" }
  return { label: "Pending", dot: "#f59e0b", className: "bg-amber-500/10 text-amber-400 border border-amber-500/20" }
}

const NAV_ITEMS = [
  {
    key: "project",
    label: "Project",
    icon: (
      <svg className="h-[18px] w-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
      </svg>
    ),
    description: "All projects",
  },
  {
    key: "edit",
    label: "Edit",
    icon: (
      <svg className="h-[18px] w-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
      </svg>
    ),
    description: "Open editor",
  },
  {
    key: "view",
    label: "View",
    icon: (
      <svg className="h-[18px] w-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
      </svg>
    ),
    description: "View clips",
  },
  {
    key: "export",
    label: "Export",
    icon: (
      <svg className="h-[18px] w-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
      </svg>
    ),
    description: "Export & publish",
  },
]

export default function DashboardPage() {
  const router = useRouter()
  const [projects, setProjects] = useState<ProjectItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [isCreating, setIsCreating] = useState(false)
  const [youtubeUrl, setYoutubeUrl] = useState("")
  const [isCreatingFromUrl, setIsCreatingFromUrl] = useState(false)
  const [isSeeding, setIsSeeding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState<Set<string>>(new Set())
  const [deleting, setDeleting] = useState<Set<string>>(new Set())
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [activeNav, setActiveNav] = useState("project")
  const [showProjectPicker, setShowProjectPicker] = useState(false)
  const [pendingNavAction, setPendingNavAction] = useState<string | null>(null)
  const [pickerSearch, setPickerSearch] = useState("")
  const [hoveredCard, setHoveredCard] = useState<string | null>(null)

  const loadProjects = useCallback(async () => {
    try {
      const response = await api.get("/api/v1/projects/")
      setProjects(Array.isArray(response.data) ? response.data : [])
    } catch { /* keep existing */ }
  }, [])

  useEffect(() => {
    const token = localStorage.getItem("token")
    if (!token) { router.push("/login"); return }
    api.get("/api/v1/projects/")
      .then((r) => setProjects(Array.isArray(r.data) ? r.data : []))
      .catch(() => setError("Could not load projects."))
      .finally(() => setIsLoading(false))
  }, [router])

  useEffect(() => {
    const hasInProgress = projects.some((p) => {
      const s = (p.status || "").toLowerCase()
      return s === "downloading" || s === "pending"
    })
    if (!hasInProgress) return
    const interval = setInterval(loadProjects, 3000)
    return () => clearInterval(interval)
  }, [projects, loadProjects])

  const stats = useMemo(() => ({
    totalProjects: projects.length,
    downloading: projects.filter((p) => (p.status || "").toLowerCase() === "downloading").length,
    ready: projects.filter((p) => (p.status || "").toLowerCase() === "ready").length,
  }), [projects])

  const handleUploadProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!uploadFile) return
    const isVercelHost = typeof window !== "undefined" && window.location.hostname.endsWith(".vercel.app")
    const apiBase = process.env.NEXT_PUBLIC_API_URL || ""
    const apiTargetsRender = /onrender\.com/i.test(apiBase)
    const VERCEL_SAFE_UPLOAD_BYTES = 4 * 1024 * 1024
    if (isVercelHost && !apiTargetsRender && uploadFile.size > VERCEL_SAFE_UPLOAD_BYTES) {
      setError("This file is too large for Vercel upload requests. Use the YouTube URL option below, or deploy backend on a VM/Render/Railway for large local uploads.")
      return
    }
    setIsCreating(true); setError(null); setUploadProgress(0)
    try {
      const formData = new FormData()
      formData.append("file", uploadFile)
      await api.post("/api/v1/uploads", formData, {
        timeout: 0,
        onUploadProgress: (e) => {
          if (e.total) setUploadProgress(Math.round((e.loaded * 100) / e.total))
        },
      })
      setUploadFile(null)
      setUploadProgress(0)
      setIsModalOpen(false)
      await loadProjects()
    } catch (err: unknown) {
      const res = (err as { response?: { status?: number; data?: { detail?: string } } })?.response
      const apiError = res?.data?.detail
      if (res?.status === 405) {
        setError("Upload API not available. Restart the backend server and try again.")
      } else if (res?.status === 413) {
        setError("Upload failed: payload too large for Vercel. Use YouTube URL import or smaller file.")
      } else {
        setError(typeof apiError === "string" ? apiError : "Could not upload video. Is the backend running?")
      }
    } finally { setIsCreating(false) }
  }

  const handleCreateFromYoutubeUrl = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = youtubeUrl.trim()
    if (!trimmed) return
    setIsCreatingFromUrl(true)
    setError(null)
    try {
      await api.post("/api/v1/projects/", { yt_url: trimmed })
      setYoutubeUrl("")
      setUploadFile(null)
      setUploadProgress(0)
      setIsModalOpen(false)
      await loadProjects()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === "string" && detail.trim() ? detail : "Could not create project from YouTube URL.")
    } finally {
      setIsCreatingFromUrl(false)
    }
  }

  const handleRetryDownload = async (e: React.MouseEvent, projectId: string) => {
    e.stopPropagation()
    setRetrying((prev) => new Set(prev).add(projectId))
    try {
      await api.post(`/api/v1/projects/${projectId}/retry-download`)
      await loadProjects()
    } catch { setError("Retry failed.") }
    finally {
      setRetrying((prev) => { const next = new Set(prev); next.delete(projectId); return next })
    }
  }

  const handleCardClick = (project: ProjectItem) => {
    const id = project.id || project._id
    if (!id) return
    router.push(`/project/${id}/clips`)
  }

  const handleDeleteProject = async (e: React.MouseEvent, projectId: string) => {
    e.stopPropagation()
    if (!window.confirm("Delete this project permanently?")) return
    setDeleting((prev) => new Set(prev).add(projectId)); setError(null)
    try {
      await api.delete(`/api/v1/projects/${projectId}`)
      await loadProjects()
    } catch { setError("Could not delete project.") }
    finally {
      setDeleting((prev) => { const next = new Set(prev); next.delete(projectId); return next })
    }
  }

  const handleSeedDummyProject = async () => {
    setIsSeeding(true); setError(null)
    try {
      await api.post("/api/v1/projects/seed-dummy", {
        file_name: "Javascript in 1 shot in Hindi  part 1-854x480-avc1-mp4a.mp4",
      })
      await loadProjects()
    } catch { setError("Could not seed dummy project.") }
    finally { setIsSeeding(false) }
  }

  const handleNavClick = (key: string) => {
    setActiveNav(key)
    if (["edit", "view", "export"].includes(key)) {
      const readyProjects = projects.filter((p) => (p.status || "").toLowerCase() === "ready")
      if (readyProjects.length === 0) {
        setError("No ready projects available. Please wait for a project to finish downloading.")
        return
      }
      setPendingNavAction(key)
      setPickerSearch("")
      setShowProjectPicker(true)
    }
  }

  // ── KEY FIX: Edit → /editor, View → /clips, Export → /publish ──
  const handleProjectSelect = (project: ProjectItem) => {
    const id = project.id || project._id
    if (!id) return
    setShowProjectPicker(false)
    if (pendingNavAction === "edit") {
      router.push(`/project/${id}/editor`)
    } else if (pendingNavAction === "view") {
      router.push(`/project/${id}/clips`)
    } else if (pendingNavAction === "export") {
      router.push(`/project/${id}/publish`)
    }
    setPendingNavAction(null)
  }

  const pickerLabel =
    pendingNavAction === "edit" ? "Choose a project to edit" :
    pendingNavAction === "view" ? "Choose a project to view clips" :
    "Choose a project to export"

  const filteredPickerProjects = projects
    .filter((p) => (p.status || "").toLowerCase() === "ready")
    .filter((p) => !pickerSearch || (p.title || "").toLowerCase().includes(pickerSearch.toLowerCase()))

  return (
    <div className="flex min-h-screen bg-[#f8fbff] text-[#0f172a]" style={{ fontFamily: "'DM Sans', sans-serif" }}>

      {/* ── SIDEBAR ── */}
      <aside className={`relative flex flex-col border-r border-slate-200/70 bg-white transition-all duration-300 ${sidebarOpen ? "w-[200px]" : "w-[52px]"}`}>
        {/* Logo */}
        <div className="flex h-[52px] items-center border-b border-white/[0.06] px-3">
          {sidebarOpen ? (
            <div className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-[#5b6ef5] to-[#8b5cf6]">
                <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                </svg>
              </div>
              <span className="text-[15px] font-bold tracking-tight text-slate-900">Movie <span className="text-[#7c8df8]">Clips</span></span>
            </div>
          ) : (
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-[#5b6ef5] to-[#8b5cf6]">
              <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
              </svg>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex flex-col gap-0.5 p-2 flex-1">
          {NAV_ITEMS.map((item) => {
            const isActive = activeNav === item.key
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => handleNavClick(item.key)}
                title={!sidebarOpen ? item.label : undefined}
                className={`group flex items-center gap-3 rounded-lg px-2.5 py-2.5 text-left transition-all duration-150 ${
                  isActive
                    ? "bg-[#5b6ef5]/15 text-[#7c8df8]"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                <span className={`flex-shrink-0 transition-colors ${isActive ? "text-[#7c8df8]" : "text-[#4a4d60]  group-hover:text-[#c8cad8]"}`}>
                  {item.icon}
                </span>
                {sidebarOpen && (
                  <span className="text-[13px] font-medium leading-none">{item.label}</span>
                )}
                {isActive && sidebarOpen && (
                  <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[#7c8df8]" />
                )}
              </button>
            )
          })}
        </nav>

        {/* Toggle + Logout */}
        <div className="border-t border-white/[0.06] p-2 space-y-0.5">
          <button
            onClick={() => setSidebarOpen((p) => !p)}
            className="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-[#4a4d60] hover:bg-white/[0.04] hover:text-[#c8cad8] transition-all"
            title={sidebarOpen ? "Collapse" : "Expand"}
          >
            <svg className="h-[18px] w-[18px] flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d={sidebarOpen ? "M11 19l-7-7 7-7M19 19l-7-7 7-7" : "M13 5l7 7-7 7M5 5l7 7-7 7"} />
            </svg>
            {sidebarOpen && <span className="text-[12px]">Collapse</span>}
          </button>
          <button
            onClick={() => { localStorage.removeItem("token"); localStorage.removeItem("refresh_token"); router.push("/login") }}
            className="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-[#4a4d60] hover:bg-red-500/10 hover:text-red-400 transition-all"
            title={!sidebarOpen ? "Logout" : undefined}
          >
            <svg className="h-[18px] w-[18px] flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            {sidebarOpen && <span className="text-[12px] font-medium">Logout</span>}
          </button>
        </div>
      </aside>

      {/* ── MAIN ── */}
      <div className="flex flex-1 flex-col min-w-0">

        {/* Top bar */}
        <header className="sticky top-0 z-40 flex h-[52px] items-center justify-between border-b border-slate-200/70 bg-white/80 px-5 backdrop-blur-xl">
          <div className="flex items-center gap-3">
            <h1 className="text-sm font-semibold text-slate-700">Dashboard</h1>
            <span className="h-4 w-px bg-white/10" />
            <span className="text-xs text-[#454760]">{stats.totalProjects} projects</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSeedDummyProject}
              disabled={isSeeding}
              className="rounded-lg border border-white/[0.08] bg-white/[0.04] px-3.5 py-1.5 text-xs font-medium text-[#9092a8] hover:bg-white/[0.07] hover:text-[#c8cad8] disabled:opacity-50 transition-all"
            >
              {isSeeding ? "Seeding…" : "Seed Demo"}
            </button>
            <button
              onClick={() => setIsModalOpen(true)}
              className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-[#5b6ef5] to-[#8b5cf6] px-4 py-1.5 text-xs font-semibold text-white shadow-lg shadow-[#5b6ef5]/25 hover:opacity-90 transition-all"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
              </svg>
              New Project
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-6 py-6">

          {/* Stats row */}
          <div className="mb-6 grid grid-cols-3 gap-3">
            {[
              { label: "Total Projects", value: stats.totalProjects, color: "from-[#5b6ef5]/20 to-transparent", accent: "#7c8df8" },
              { label: "Processing", value: stats.downloading, color: "from-[#3b82f6]/20 to-transparent", accent: "#60a5fa" },
              { label: "Ready", value: stats.ready, color: "from-[#10b981]/20 to-transparent", accent: "#34d399" },
            ].map((stat) => (
              <div key={stat.label} className="relative overflow-hidden rounded-xl border border-slate-200/70 bg-white p-4">
                <div className={`absolute inset-0 bg-gradient-to-br ${stat.color} pointer-events-none`} />
                <p className="text-xs text-[#5a5d72] mb-1">{stat.label}</p>
                <p className="text-3xl font-black" style={{ color: stat.accent }}>{stat.value}</p>
              </div>
            ))}
          </div>

          {error && (
            <div className="mb-4 flex items-center justify-between rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3">
              <p className="text-sm text-red-400">{error}</p>
              <button onClick={() => setError(null)} className="text-red-400/60 hover:text-red-400 text-lg leading-none">✕</button>
            </div>
          )}

          {/* Projects grid */}
          {isLoading ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {[1,2,3].map(i => (
                <div key={i} className="rounded-xl border border-slate-200/70 bg-white p-3 animate-pulse">
                  <div className="aspect-video rounded-lg bg-slate-100 mb-3" />
                  <div className="h-4 w-3/4 rounded bg-white/[0.04] mb-2" />
                  <div className="h-3 w-1/3 rounded bg-white/[0.04]" />
                </div>
              ))}
            </div>
          ) : projects.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200/70 bg-white py-20 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[#5b6ef5]/10">
                <svg className="h-7 w-7 text-[#5b6ef5]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                </svg>
              </div>
              <p className="text-sm font-medium text-[#6b6e84]">No projects yet</p>
              <p className="mt-1 text-xs text-[#3a3d52]">Click <span className="text-[#7c8df8]">New Project</span> to upload a 1–2 hour video</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {projects.map((project) => {
                const id = project.id || project._id || ""
                const st = (project.status || "pending").toLowerCase()
                const badge = statusBadge(st)
                const isRetryable = st === "error"
                const isRetryingThis = retrying.has(id)
                const isDeletingThis = deleting.has(id)
                const isHovered = hoveredCard === id
                const token = typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""
                const seededThumbnailUrl = id && token
                  ? `${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/projects/${id}/thumbnail?token=${token}`
                  : null
                const cardThumbnailUrl = project.thumbnail_url || (project.metadata?.seeded ? seededThumbnailUrl : null)

                return (
                  <article
                    key={id || project.title}
                    onClick={() => handleCardClick(project)}
                    onMouseEnter={() => setHoveredCard(id)}
                    onMouseLeave={() => setHoveredCard(null)}
                    className="group cursor-pointer rounded-xl border border-slate-200/70 bg-white p-3 shadow-sm transition-all duration-200 hover:border-blue-300/40 hover:shadow-[0_0_20px_rgba(59,130,246,0.08)]"
                  >
                    {/* Thumbnail */}
                    <div className="relative mb-3 aspect-video overflow-hidden rounded-lg bg-slate-100">
                      {cardThumbnailUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={cardThumbnailUrl} alt={project.title || "Project"} className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" />
                      ) : (
                        <div className="flex h-full items-center justify-center">
                          <svg className="h-10 w-10 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                          </svg>
                        </div>
                      )}

                      {/* Duration badge */}
                      <div className="absolute bottom-2 right-2 rounded-md bg-black/70 px-1.5 py-0.5 text-[11px] font-mono text-white/90 backdrop-blur-sm">
                        {formatDuration(project.duration_seconds)}
                      </div>

                      {/* Hover overlay */}
                      <div className={`absolute inset-0 flex items-center justify-center bg-black/40 backdrop-blur-[1px] transition-opacity duration-200 ${isHovered ? "opacity-100" : "opacity-0"}`}>
                        <div className="flex items-center gap-1.5 rounded-full bg-white/90 px-3 py-1.5">
                          <svg className="h-3.5 w-3.5 text-[#191b23]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                          </svg>
                          <span className="text-xs font-semibold text-[#191b23]">Open</span>
                        </div>
                      </div>
                    </div>

                    <h3 className="line-clamp-1 text-sm font-medium text-[#c8cad8]">{project.title || "Untitled Project"}</h3>

                    <div className="mt-2.5 flex items-center justify-between gap-2">
                      <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${badge.className}`}>
                        <span className="h-1.5 w-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: badge.dot }} />
                        {badge.label}
                      </span>

                      <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                        {isRetryable && (
                          <button
                            onClick={(e) => handleRetryDownload(e, id)}
                            disabled={isRetryingThis || isDeletingThis}
                            className="rounded-md bg-[#5b6ef5]/20 px-2 py-1 text-[11px] font-medium text-[#7c8df8] hover:bg-[#5b6ef5]/30 disabled:opacity-50 transition-all"
                          >
                            {isRetryingThis ? "Retrying…" : "Retry"}
                          </button>
                        )}
                        <button
                          onClick={(e) => handleDeleteProject(e, id)}
                          disabled={isDeletingThis || isRetryingThis}
                          className="rounded-md border border-red-500/20 px-2 py-1 text-[11px] font-medium text-red-400/80 hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50 transition-all"
                        >
                          {isDeletingThis ? "…" : "Delete"}
                        </button>
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </main>
      </div>

      {/* ── PROJECT PICKER MODAL ── */}
      {showProjectPicker && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.7)" }}>
          <div
            className="w-full max-w-[500px] overflow-hidden rounded-2xl border border-white/[0.08] shadow-2xl"
            style={{ background: "linear-gradient(145deg, #16161f, #12121a)" }}
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-4">
              <div>
                <h2 className="text-base font-bold text-white">{pickerLabel}</h2>
                <p className="mt-0.5 text-xs text-[#5a5d72]">
                  {pendingNavAction === "edit" && "Select a project to open in the editor"}
                  {pendingNavAction === "view" && "Select a project to view its clips"}
                  {pendingNavAction === "export" && "Select a project to publish"}
                </p>
              </div>
              <button
                onClick={() => setShowProjectPicker(false)}
                className="flex h-7 w-7 items-center justify-center rounded-lg text-[#4a4d60] hover:bg-white/[0.06] hover:text-[#c8cad8] transition-all"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Search */}
            <div className="px-4 pt-3 pb-2">
              <div className="flex items-center gap-2 rounded-lg border border-white/[0.07] bg-white/[0.04] px-3 py-2">
                <svg className="h-3.5 w-3.5 text-[#4a4d60]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  value={pickerSearch}
                  onChange={(e) => setPickerSearch(e.target.value)}
                  placeholder="Search projects…"
                  className="flex-1 bg-transparent text-xs text-[#c8cad8] outline-none placeholder:text-[#3a3d52]"
                  autoFocus
                />
              </div>
            </div>

            {/* Project list */}
            <div className="max-h-[340px] overflow-y-auto px-4 pb-4 space-y-2">
              {filteredPickerProjects.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-center">
                  <p className="text-sm text-[#4a4d60]">No ready projects found</p>
                </div>
              ) : filteredPickerProjects.map((project) => {
                const id = project.id || project._id || ""
                const token = typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""
                const thumb = project.thumbnail_url ||
                  (project.metadata?.seeded
                    ? `${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/projects/${id}/thumbnail?token=${token}`
                    : null)
                return (
                  <button
                    key={id}
                    onClick={() => handleProjectSelect(project)}
                    className="group flex w-full items-center gap-3 rounded-xl border border-white/[0.05] bg-white/[0.03] p-3 text-left transition-all hover:border-[#5b6ef5]/40 hover:bg-[#5b6ef5]/5"
                  >
                    <div className="h-12 w-20 flex-shrink-0 overflow-hidden rounded-lg bg-[#1a1a23]">
                      {thumb ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={thumb} alt={project.title || ""} className="h-full w-full object-cover" />
                      ) : (
                        <div className="flex h-full items-center justify-center">
                          <svg className="h-5 w-5 text-[#2a2d3e]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                          </svg>
                        </div>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="truncate text-sm font-medium text-slate-900 group-hover:text-slate-900">{project.title || "Untitled Project"}</p>
                      <p className="mt-0.5 text-xs text-slate-500">{formatDuration(project.duration_seconds)}</p>
                    </div>
                    <svg className="h-4 w-4 flex-shrink-0 text-[#3a3d52] group-hover:text-[#7c8df8] transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* ── NEW PROJECT MODAL ── */}
      {isModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.7)" }}>
          <div
            className="w-full max-w-[460px] overflow-hidden rounded-2xl border border-white/[0.08] shadow-2xl"
            style={{ background: "linear-gradient(145deg, #16161f, #12121a)" }}
          >
            <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-4">
              <div>
                <h2 className="text-base font-bold text-white">Upload Movie</h2>
                <p className="mt-0.5 text-xs text-[#5a5d72]">Upload a video (MP4, MOV, WebM, MKV) or paste a YouTube URL.</p>
              </div>
              <button onClick={() => setIsModalOpen(false)} className="flex h-7 w-7 items-center justify-center rounded-lg text-[#4a4d60] hover:bg-white/[0.06] hover:text-[#c8cad8] transition-all">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handleUploadProject} className="p-5 space-y-4">
              {error && <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

              <div>
                <label className="mb-2 block text-[11px] font-semibold uppercase tracking-wider text-[#4a4d60]">Video file</label>
                <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/[0.12] bg-white/[0.04] px-4 py-8 transition-colors hover:border-[#5b6ef5]/50">
                  <svg className="h-8 w-8 text-[#7c8df8]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <span className="text-sm font-medium text-[#c8cad8]">
                    {uploadFile ? uploadFile.name : "Choose MP4, MOV, or MKV (up to 5 GB)"}
                  </span>
                  <span className="text-xs text-[#5a5d72]">1–2 hour movies supported</span>
                  <input
                    type="file"
                    accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.mkv,.webm"
                    className="hidden"
                    onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                  />
                </label>
                {isCreating && uploadProgress > 0 && (
                  <div className="mt-3">
                    <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.08]">
                      <div className="h-full rounded-full bg-gradient-to-r from-[#5b6ef5] to-[#8b5cf6] transition-all" style={{ width: `${uploadProgress}%` }} />
                    </div>
                    <p className="mt-1 text-center text-xs text-[#5a5d72]">{uploadProgress}% uploaded</p>
                  </div>
                )}
              </div>

              <div className="flex items-center gap-3 pt-1">
                <button type="button" onClick={() => { setIsModalOpen(false); setError(null); setUploadFile(null) }}
                  className="flex-1 rounded-xl border border-white/[0.07] py-2.5 text-sm font-medium text-[#6b6e84] hover:bg-white/[0.04] hover:text-[#c8cad8] transition-all">
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreating || !uploadFile}
                  className="flex-1 rounded-xl bg-gradient-to-r from-[#5b6ef5] to-[#8b5cf6] py-2.5 text-sm font-semibold text-white shadow-lg shadow-[#5b6ef5]/20 hover:opacity-90 disabled:opacity-50 transition-all"
                >
                  {isCreating ? "Uploading…" : "Upload & Cut Clips"}
                </button>
              </div>
            </form>

            <div className="border-t border-white/[0.06] px-5 pb-5 pt-4">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-[#4a4d60]">YouTube URL (recommended on Vercel)</p>
              <form onSubmit={handleCreateFromYoutubeUrl} className="space-y-3">
                <input
                  type="url"
                  required
                  value={youtubeUrl}
                  onChange={(e) => setYoutubeUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=..."
                  className="w-full rounded-xl border border-white/[0.12] bg-white/[0.04] px-3 py-2.5 text-sm text-[#c8cad8] outline-none placeholder:text-[#5a5d72] focus:border-[#5b6ef5]/60"
                />
                <button
                  type="submit"
                  disabled={isCreatingFromUrl}
                  className="w-full rounded-xl border border-[#5b6ef5]/40 bg-[#5b6ef5]/15 py-2.5 text-sm font-semibold text-[#aeb8ff] hover:bg-[#5b6ef5]/25 disabled:opacity-50 transition-all"
                >
                  {isCreatingFromUrl ? "Creating…" : "Create Project from URL"}
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}