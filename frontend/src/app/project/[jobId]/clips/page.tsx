"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import api from "@/lib/api"

type ProjectData = {
  id?: string
  _id?: string
  title?: string
  status?: string
  cloudinary_raw_url?: string | null
  local_video_path?: string | null
  thumbnail_url?: string | null
  duration_seconds?: number | null
  yt_url?: string
  created_at?: string
  metadata?: Record<string, unknown> | null
}

type ClipData = {
  id?: string
  _id?: string
  label?: string | null
  start_time?: number
  end_time?: number
  duration?: number
  status?: string
  cloudinary_clip_url?: string | null
  thumbnail_url?: string | null
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
  if (s === "ready") return { label: "Ready", className: "bg-emerald-100 text-emerald-700" }
  if (s === "downloading") return { label: "Downloading…", className: "bg-blue-100 text-blue-700 animate-pulse" }
  if (s === "error") return { label: "Error", className: "bg-red-100 text-red-700" }
  if (s === "processing") return { label: "Processing…", className: "bg-violet-100 text-violet-700 animate-pulse" }
  return { label: "Pending", className: "bg-amber-100 text-amber-700" }
}

export default function ProjectClipsPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.jobId as string

  const [project, setProject] = useState<ProjectData | null>(null)
  const [clips, setClips] = useState<ClipData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState(false)

  const loadProject = useCallback(async () => {
    try {
      const [projRes, clipsRes] = await Promise.all([
        api.get(`/api/v1/projects/${projectId}`),
        api.get(`/api/v1/projects/${projectId}/clips`),
      ])
      setProject(projRes.data)
      setClips(Array.isArray(clipsRes.data) ? clipsRes.data : [])
    } catch {
      setError("Could not load project.")
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    const token = localStorage.getItem("token")
    if (!token) {
      router.push("/login")
      return
    }
    loadProject()
  }, [loadProject, router])

  // Auto-refresh while downloading
  useEffect(() => {
    const s = (project?.status || "").toLowerCase()
    if (s !== "downloading" && s !== "pending") return
    const interval = setInterval(loadProject, 5000)
    return () => clearInterval(interval)
  }, [project?.status, loadProject])

  const handleRetry = async () => {
    setRetrying(true)
    try {
      await api.post(`/api/v1/projects/${projectId}/retry-download`)
      await loadProject()
    } catch {
      setError("Retry failed.")
    } finally {
      setRetrying(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#faf8ff]">
        <p className="text-sm text-[#737686]">Loading project…</p>
      </div>
    )
  }

  if (error || !project) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#faf8ff]">
        <p className="text-sm text-red-600">{error || "Project not found."}</p>
        <button onClick={() => router.push("/dashboard")} className="text-sm font-medium text-[#004ac6] underline">
          ← Back to Dashboard
        </button>
      </div>
    )
  }

  const st = (project.status || "pending").toLowerCase()
  const badge = statusBadge(st)
  const isRetryable = st === "pending" || st === "error"
  const errorMessage = (project.metadata as Record<string, string> | null)?.error_message

  return (
    <div className="min-h-screen bg-[#faf8ff] text-[#191b23]">
      {/* Header */}
      <header className="sticky top-0 z-40 flex h-12 items-center justify-between border-b border-[#e1e2ed] bg-white/70 px-4 shadow-[0_2px_10px_-3px_rgba(0,0,0,0.07)] backdrop-blur-xl">
        <div className="flex items-center gap-4">
          <button onClick={() => router.push("/dashboard")} className="text-sm font-medium text-[#004ac6] hover:underline">
            ← Dashboard
          </button>
          <span className="text-sm text-[#c3c6d7]">|</span>
          <span className="text-sm font-bold truncate max-w-[300px]">{project.title || "Untitled Project"}</span>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {/* Project info bar */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">{project.title || "Untitled Project"}</h1>
            <div className="mt-1 flex items-center gap-3">
              <span className={`inline-block rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${badge.className}`}>
                {badge.label}
              </span>
              <span className="text-xs text-[#737686]">{formatDuration(project.duration_seconds)}</span>
            </div>
          </div>
          {isRetryable && (
            <button
              onClick={handleRetry}
              disabled={retrying}
              className="rounded-lg bg-[#004ac6] px-5 py-2 text-sm font-medium text-white shadow-sm hover:bg-[#0053db] disabled:opacity-50"
            >
              {retrying ? "Retrying…" : "Retry Download"}
            </button>
          )}
        </div>

        {/* Error banner */}
        {st === "error" && errorMessage && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <strong>Download failed:</strong> {errorMessage}
          </div>
        )}

        {/* Video Player Section */}
        <div className="mb-8">
          {st === "ready" && (project.local_video_path || project.cloudinary_raw_url) ? (
            <div className="overflow-hidden rounded-xl border border-[#e1e2ed] bg-black shadow-lg">
              <video
                controls
                preload="metadata"
                poster={project.thumbnail_url || undefined}
                className="w-full aspect-video"
                src={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/projects/${projectId}/stream?token=${typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""}`}
              >
                Your browser does not support the video tag.
              </video>
            </div>
          ) : st === "downloading" ? (
            <div className="flex aspect-video items-center justify-center rounded-xl border border-[#e1e2ed] bg-[#ededf9]">
              <div className="text-center">
                <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-4 border-[#004ac6] border-t-transparent" />
                <p className="text-sm font-medium text-[#434655]">Downloading video from YouTube…</p>
                <p className="mt-1 text-xs text-[#737686]">This may take a few minutes depending on video length.</p>
              </div>
            </div>
          ) : st === "pending" ? (
            <div className="flex aspect-video items-center justify-center rounded-xl border border-dashed border-[#c3c6d7] bg-[#ededf9]">
              <div className="text-center">
                <p className="text-sm font-medium text-[#434655]">Download not started</p>
                <p className="mt-1 text-xs text-[#737686]">Click &quot;Retry Download&quot; to start downloading this video.</p>
              </div>
            </div>
          ) : st === "error" ? (
            <div className="flex aspect-video items-center justify-center rounded-xl border border-red-200 bg-red-50">
              <div className="text-center">
                <p className="text-sm font-medium text-red-600">Download failed</p>
                <p className="mt-1 text-xs text-red-500">Click &quot;Retry Download&quot; above to try again.</p>
              </div>
            </div>
          ) : (
            <div className="flex aspect-video items-center justify-center rounded-xl border border-[#e1e2ed] bg-[#ededf9]">
              <p className="text-sm text-[#737686]">Video not available</p>
            </div>
          )}
        </div>

        {/* Clips Section */}
        <div>
          <h2 className="mb-4 text-lg font-bold">Clips</h2>
          {clips.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[#c3c6d7] bg-white p-8 text-center text-sm text-[#434655]">
              {st === "ready"
                ? "No clips yet. Use the editor to create clips from this video."
                : "Clips will be available once the video download is complete."}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {clips.map((clip) => {
                const clipId = clip.id || clip._id || ""
                const clipBadge = statusBadge(clip.status || "pending")
                return (
                  <div
                    key={clipId}
                    className="rounded-xl border border-[#e1e2ed] bg-white p-3 shadow-sm"
                  >
                    <div className="relative mb-3 aspect-video overflow-hidden rounded-lg bg-[#ededf9]">
                      {clip.status === "ready" && clip.cloudinary_clip_url ? (
                        <video
                          controls
                          preload="metadata"
                          poster={clip.thumbnail_url || undefined}
                          className="h-full w-full object-cover"
                          src={clip.cloudinary_clip_url}
                        />
                      ) : clip.thumbnail_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={clip.thumbnail_url} alt={clip.label || "Clip"} className="h-full w-full object-cover" />
                      ) : (
                        <div className="flex h-full items-center justify-center text-xs text-[#737686]">No preview</div>
                      )}
                      <div className="absolute bottom-2 right-2 rounded bg-black/70 px-2 py-0.5 text-[11px] text-white">
                        {formatDuration(clip.duration)}
                      </div>
                    </div>
                    <h3 className="text-sm font-medium">{clip.label || `Clip ${formatDuration(clip.start_time)} – ${formatDuration(clip.end_time)}`}</h3>
                    <span className={`mt-1 inline-block rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${clipBadge.className}`}>
                      {clipBadge.label}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
