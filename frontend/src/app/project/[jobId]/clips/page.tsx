"use client"

import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react"
import { useParams, useRouter } from "next/navigation"
import api from "@/lib/api"

// ── Types ──────────────────────────────────────────────────────────────────
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
  source_file_available?: boolean
  is_upload?: boolean
  has_cloudinary_raw?: boolean
  needs_reupload?: boolean
  pipeline_running?: boolean
  processing_step?: string | null
  created_at?: string
  summary?: string | null
  summary_status?: string | null
  summary_error?: string | null
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

// ── Helpers ────────────────────────────────────────────────────────────────
function formatDuration(totalSeconds?: number | null) {
  if (!totalSeconds || totalSeconds < 1) return "--:--"
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = Math.floor(totalSeconds % 60)
  if (hours > 0)
    return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`
}

function formatTime(s?: number) {
  if (s === undefined || s === null || s < 0) return "0:00"
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, "0")}`
}

function apiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_URL || ""
}

function clipStreamUrl(projectId: string, clipId: string, token: string) {
  return `${apiBaseUrl()}/api/v1/projects/${projectId}/clips/${clipId}/stream?token=${encodeURIComponent(token)}`
}

function clipThumbnailUrl(projectId: string, clipId: string, token: string, cloudinaryUrl?: string | null) {
  if (cloudinaryUrl) return cloudinaryUrl
  if (!token) return null
  return `${apiBaseUrl()}/api/v1/projects/${projectId}/clips/${clipId}/thumbnail?token=${encodeURIComponent(token)}`
}

function getApiErrorDetail(err: unknown, fallback: string) {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return typeof detail === "string" ? detail : fallback
}

function getClipPartLabel(clip: ClipData, partNumber: number): string {
  const label = (clip.label || "").trim()
  if (label) return label
  return `Part-${partNumber}`
}

function statusBadge(status: string) {
  const s = status.toLowerCase()
  if (s === "ready") return { label: "Ready", dot: "#10b981", className: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" }
  if (s === "downloading") return { label: "Downloading…", dot: "#3b82f6", className: "bg-blue-500/10 text-blue-400 border border-blue-500/20 animate-pulse" }
  if (s === "error") return { label: "Error", dot: "#ef4444", className: "bg-red-500/10 text-red-400 border border-red-500/20" }
  if (s === "processing") return { label: "Processing…", dot: "#a855f7", className: "bg-purple-500/10 text-purple-400 border border-purple-500/20 animate-pulse" }
  return { label: "Pending", dot: "#f59e0b", className: "bg-amber-500/10 text-amber-400 border border-amber-500/20" }
}

// ── Icons ──────────────────────────────────────────────────────────────────
function PlayIcon() {
  return (
    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
      <path d="M8 5v14l11-7z" />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  )
}

function EditIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
    </svg>
  )
}

// ── Clip Modal ─────────────────────────────────────────────────────────────
function ClipModal({
  clip,
  projectId,
  token,
  displayLabel,
  onClose,
  onDelete,
  onSavedRemote,
}: {
  clip: ClipData
  projectId: string
  token: string
  displayLabel: string
  onClose: () => void
  onDelete: (clipId: string) => void
  onSavedRemote: (url: string) => void
}) {
  const clipId = clip.id || clip._id || ""
  const badge = statusBadge(clip.status || "pending")
  const [isDeleting, setIsDeleting] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [playbackError, setPlaybackError] = useState<string | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const isReady = (clip.status || "").toLowerCase() === "ready"

  const videoSrc = clip.cloudinary_clip_url
    ? clip.cloudinary_clip_url
    : isReady
      ? clipStreamUrl(projectId, clipId, token)
      : ""

  const posterUrl = clipThumbnailUrl(projectId, clipId, token, clip.thumbnail_url)

  useEffect(() => {
    setPlaybackError(null)
  }, [clipId, videoSrc])

  const handleDownload = async (e?: MouseEvent) => {
    e?.stopPropagation()
    if (!isReady || !token || isSaving) return
    setIsSaving(true)
    try {
      const res = await api.post(`/api/v1/projects/${projectId}/clips/${clipId}/save-remote`)
      const url = res.data?.url as string | undefined
      if (url) onSavedRemote(url)
      else window.alert("Saved to hosting, but no public URL was returned.")
    } catch (err: unknown) {
      window.alert(getApiErrorDetail(err, "Could not save clip to hosting."))
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm("Delete this clip permanently?")) return
    setIsDeleting(true)
    try {
      await api.delete(`/api/v1/clips/${clipId}`)
      onDelete(clipId)
      onClose()
    } catch {
      window.alert("Could not delete clip.")
    } finally {
      setIsDeleting(false)
    }
  }

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [onClose])

  // Pause video when modal closes
  useEffect(() => {
    return () => { videoRef.current?.pause() }
  }, [])

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-white/90 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="w-full max-w-[780px] overflow-hidden rounded-2xl border border-slate-200/70 shadow-2xl"
        style={{ background: "linear-gradient(145deg, #ffffff, #eff6ff)" }}
      >
        {/* Modal header */}
        <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3.5">
          <div className="flex items-center gap-3 min-w-0">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium flex-shrink-0 ${badge.className}`}>
              <span className="h-1.5 w-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: badge.dot }} />
              {badge.label}
            </span>
            <h2 className="text-sm font-semibold text-[#c8cad8] truncate">
              {displayLabel}
            </h2>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Save to hosting */}
            {clip.status === "ready" && (
              <button
                onClick={handleDownload}
                disabled={isSaving}
                className="flex items-center gap-1.5 rounded-lg border border-slate-200/70 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-blue-50 hover:text-blue-700 hover:border-blue-100 disabled:opacity-50 transition-all"
              >
                <DownloadIcon />
                {isSaving ? "Saving…" : "Save to hosting"}
              </button>
            )}
            {/* Delete */}
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className="flex items-center gap-1.5 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-1.5 text-xs font-medium text-red-400/80 hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50 transition-all"
            >
              <TrashIcon />
              {isDeleting ? "Deleting…" : "Delete"}
            </button>
            {/* Close */}
            <button
              onClick={onClose}
              className="flex h-7 w-7 items-center justify-center rounded-lg text-[#4a4d60] hover:bg-white/[0.06] hover:text-[#c8cad8] transition-all"
            >
              <CloseIcon />
            </button>
          </div>
        </div>

        {/* Video player */}
        <div className="bg-slate-100">
          {clip.status === "ready" && videoSrc && !playbackError ? (
            <video
              ref={videoRef}
              src={videoSrc}
              controls
              autoPlay
              poster={posterUrl || undefined}
              onError={() =>
                setPlaybackError(
                  "Clip file is missing on the server. For uploads, re-upload the video. For YouTube, use Refetch source.",
                )
              }
              className="w-full max-h-[440px] object-contain"
            />
          ) : (
            <div className="flex aspect-video items-center justify-center px-6">
              <div className="text-center max-w-md">
                {playbackError ? (
                  <p className="text-sm text-red-600">{playbackError}</p>
                ) : (
                  <>
                    <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-[#5b6ef5] border-t-transparent" />
                    <p className="text-sm text-[#4a4d60]">
                      {clip.status === "processing" ? "Clip is being processed…" : "Clip not ready yet"}
                    </p>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Clip info footer */}
        <div className="flex items-center gap-6 border-t border-white/[0.06] px-5 py-3">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-[#4a4d60]">Duration</span>
            <span className="text-[11px] font-mono font-medium text-[#8082a0]">{formatDuration(clip.duration)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-[#4a4d60]">Start</span>
            <span className="text-[11px] font-mono font-medium text-[#8082a0]">{formatTime(clip.start_time)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-[#4a4d60]">End</span>
            <span className="text-[11px] font-mono font-medium text-[#8082a0]">{formatTime(clip.end_time)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────
export default function ProjectClipsPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.jobId as string

  const [project, setProject] = useState<ProjectData | null>(null)
  const [clips, setClips] = useState<ClipData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [selectedClip, setSelectedClip] = useState<ClipData | null>(null)
  const [hoveredCard, setHoveredCard] = useState<string | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isRetrying, setIsRetrying] = useState(false)
  const [downloadingClipId, setDownloadingClipId] = useState<string | null>(null)
  const [isDownloadingAll, setIsDownloadingAll] = useState(false)
  const [isRefetchingSource, setIsRefetchingSource] = useState(false)
  const [saveNotice, setSaveNotice] = useState<string | null>(null)
  const hasLoadedProject = useRef(false)

  const token = typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""

  const loadProject = useCallback(async () => {
    try {
      const projRes = await api.get(`/api/v1/projects/${projectId}`, { timeout: 60000 })
      setProject(projRes.data)
      hasLoadedProject.current = true
      setError(null)
      try {
        const clipsRes = await api.get(`/api/v1/projects/${projectId}/clips`, { timeout: 60000 })
        setClips(Array.isArray(clipsRes.data) ? clipsRes.data : [])
      } catch {
        // Project loaded; clips can appear on the next poll.
      }
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      const isTimeout =
        (err as { code?: string })?.code === "ECONNABORTED" ||
        String((err as { message?: string })?.message || "").toLowerCase().includes("timeout")
      if (!hasLoadedProject.current) {
        setError(
          isTimeout || !status
            ? "Server is still processing this video. Retrying…"
            : "Could not load project."
        )
      }
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    const t = localStorage.getItem("token")
    if (!t) { router.push("/login"); return }
    if (!projectId || projectId === "undefined") { router.push("/dashboard"); return }
    loadProject()
  }, [loadProject, router, projectId])

  // Poll while project is processing, clips are in progress, or first load is still retrying
  useEffect(() => {
    const projectBusy =
      ["downloading", "pending"].includes((project?.status || "").toLowerCase()) ||
      project?.pipeline_running === true
    const clipsBusy = clips.some((c) => {
      const s = (c.status || "").toLowerCase()
      return s === "processing" || s === "pending"
    })
    const waitingToLoad = !project && /processing|retrying/i.test(error || "")
    if (!projectBusy && !clipsBusy && !waitingToLoad) return
    const interval = setInterval(loadProject, waitingToLoad ? 3000 : 5000)
    return () => clearInterval(interval)
  }, [clips, project?.status, project?.pipeline_running, loadProject, project, error])

  const handleClipDeleted = (clipId: string) => {
    setClips((prev) => prev.filter((c) => (c.id || c._id) !== clipId))
  }

  const SEGMENT_60_SEC = 60

  const handleRetryProcessing = async () => {
    setIsRetrying(true)
    setError(null)
    try {
      const upload =
        project?.is_upload === true ||
        project?.metadata?.source === "upload" ||
        (project?.yt_url || "").startsWith("upload://")
      await api.post(
        upload
          ? `/api/v1/projects/${projectId}/retry-processing`
          : `/api/v1/projects/${projectId}/retry-download`,
      )
      await loadProject()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === "string" ? detail : "Could not retry processing.")
      await loadProject()
    } finally {
      setIsRetrying(false)
    }
  }

  const handleRefetchSource = async () => {
    setIsRefetchingSource(true)
    setError(null)
    try {
      const res = await api.post(`/api/v1/projects/${projectId}/refetch-source`)
      const message = (res.data?.message as string | undefined) || "Re-fetching source video…"
      setSaveNotice(message)
      await loadProject()
    } catch (err: unknown) {
      setError(getApiErrorDetail(err, "Could not re-fetch source video."))
    } finally {
      setIsRefetchingSource(false)
    }
  }

  const handleGenerateClips = async (segmentSeconds: number = SEGMENT_60_SEC) => {
    setIsGenerating(true); setError(null)
    try {
      await api.post(`/api/v1/projects/${projectId}/generate-clips`, null, {
        params: { segment_seconds: segmentSeconds },
      })
      // Keep UI in generating state until clips appear (or warning/error).
      const deadline = Date.now() + 5 * 60 * 1000
      while (Date.now() < deadline) {
        const [projRes, clipsRes] = await Promise.all([
          api.get(`/api/v1/projects/${projectId}`),
          api.get(`/api/v1/projects/${projectId}/clips`),
        ])
        const nextProject = projRes.data
        const nextClips = Array.isArray(clipsRes.data) ? clipsRes.data : []
        setProject(nextProject)
        setClips(nextClips)
        const warning =
          typeof nextProject?.metadata?.auto_clip_warning === "string"
            ? nextProject.metadata.auto_clip_warning.trim()
            : ""
        if (warning) {
          setError(warning)
          break
        }
        if (nextClips.length > 0) break
        await new Promise((r) => setTimeout(r, 2000))
      }
    } catch (err: unknown) {
      setError(
        getApiErrorDetail(err, "Could not start clip generation. Make sure the video is Ready.")
      )
    } finally {
      setIsGenerating(false)
    }
  }

  const handleDownloadClip = async (clip: ClipData, partNumber: number, e?: MouseEvent) => {
    e?.stopPropagation()
    const clipId = clip.id || clip._id || ""
    if (!clipId || !token) return
    if ((clip.status || "").toLowerCase() !== "ready") return
    setDownloadingClipId(clipId)
    setError(null)
    try {
      const res = await api.post(`/api/v1/projects/${projectId}/clips/${clipId}/save-remote`)
      const url = res.data?.url as string | undefined
      setSaveNotice(url ? `Saved to hosting: ${url}` : "Saved to hosting.")
    } catch (err: unknown) {
      setError(getApiErrorDetail(err, "Could not save clip to hosting."))
    } finally {
      setDownloadingClipId(null)
    }
  }

  const handleDownloadAll = async () => {
    const readyClips = clips.filter((c) => (c.status || "").toLowerCase() === "ready")
    if (!token || readyClips.length === 0) return
    setIsDownloadingAll(true)
    setError(null)
    try {
      const res = await api.post(`/api/v1/projects/${projectId}/clips/save-all-remote`)
      const count = res.data?.count ?? readyClips.length
      const folderUrl = res.data?.folder_url as string | undefined
      setSaveNotice(
        folderUrl
          ? `Saved ${count} clip${count === 1 ? "" : "s"} to hosting: ${folderUrl}`
          : `Saved ${count} clip${count === 1 ? "" : "s"} to hosting.`,
      )
    } catch (err: unknown) {
      setError(getApiErrorDetail(err, "Could not save clips to hosting."))
    } finally {
      setIsDownloadingAll(false)
    }
  }

  const sortedClips = useMemo(
    () => [...clips].sort((a, b) => (a.start_time ?? 0) - (b.start_time ?? 0)),
    [clips],
  )

  const getPartNumber = useCallback(
    (clip: ClipData) => {
      const id = clip.id || clip._id || ""
      const idx = sortedClips.findIndex((c) => (c.id || c._id) === id)
      return idx >= 0 ? idx + 1 : 1
    },
    [sortedClips],
  )

  // ── Loading ──
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f8fbff]">
        <div className="text-center">
          <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-blue-400 border-t-transparent" />
          <p className="text-sm text-slate-500">Loading clips…</p>
        </div>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#f8fbff]">
        <p className="text-sm text-red-500">{error || "Project not found."}</p>
        <div className="flex items-center gap-3">
          <button
            onClick={() => { setLoading(true); setError(null); void loadProject() }}
            className="rounded-lg bg-[#2563eb] px-4 py-2 text-sm font-medium text-white"
          >
            Retry
          </button>
          <button onClick={() => router.push("/dashboard")} className="text-sm font-medium text-[#1a73e8] hover:underline">
            ← Back to Dashboard
          </button>
        </div>
      </div>
    )
  }

  const projectStatus = (project.status || "pending").toLowerCase()
  const projectBadge = statusBadge(projectStatus)

  const readyCount = clips.filter((c) => (c.status || "").toLowerCase() === "ready").length
  const errorCount = clips.filter((c) => (c.status || "").toLowerCase() === "error").length
  const isProcessingUpload = projectStatus === "downloading" || projectStatus === "pending"
  const pipelineRunning = project.pipeline_running === true
  const processingStep =
    typeof project.processing_step === "string" && project.processing_step.trim()
      ? project.processing_step.trim()
      : typeof project.metadata?.processing_step === "string"
        ? project.metadata.processing_step.trim()
        : ""
  const isUpload =
    project.is_upload === true ||
    project.metadata?.source === "upload" ||
    (project.yt_url || "").startsWith("upload://")
  const rawError =
    typeof project.metadata?.error_message === "string" ? project.metadata.error_message.trim() : ""
  const rawWarning =
    typeof project.metadata?.auto_clip_warning === "string" ? project.metadata.auto_clip_warning.trim() : ""
  // Hide misleading yt-dlp errors on manual uploads (upload:// scheme).
  const cleanedError =
    isUpload && /unsupported url scheme.*upload|yt-dlp/i.test(rawError) ? "" : rawError
  const missingSourceMessage = /no longer on the server|upload the video again/i.test(cleanedError || "")
  const ffmpegFalseAlarm =
    isUpload && /ffmpeg\/ffprobe is not installed/i.test(cleanedError || "")
  const processingError =
    missingSourceMessage || ffmpegFalseAlarm
      ? null
      : cleanedError ||
        rawWarning ||
        (projectStatus === "error"
          ? isUpload
            ? "Upload processing failed. Re-upload the video from the dashboard."
            : "Video processing failed. Install FFmpeg, restart the backend, then click Retry processing."
          : null)
  const canGenerate = projectStatus === "ready" && !isProcessingUpload
  const sourceMissing = project.source_file_available === false
  const needsRefetch = !isUpload && !isProcessingUpload && sourceMissing && readyCount > 0 && !!project.yt_url
  const needsReupload =
    isUpload &&
    !pipelineRunning &&
    (project.needs_reupload === true ||
      missingSourceMessage ||
      ffmpegFalseAlarm ||
      (sourceMissing && !project.has_cloudinary_raw && !project.cloudinary_raw_url && !isProcessingUpload))
  const canRestoreUpload =
    isUpload &&
    !isProcessingUpload &&
    sourceMissing &&
    !!(project.has_cloudinary_raw || project.cloudinary_raw_url)

  return (
    <div
      className="min-h-screen bg-[#f8fbff] text-[#0f172a]"
      style={{ fontFamily: "'DM Sans', sans-serif" }}
    >
      {/* ── HEADER ── */}
      <header className="sticky top-0 z-40 flex h-[52px] items-center justify-between border-b border-slate-200/70 bg-white/80 px-5 backdrop-blur-xl">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => router.push("/dashboard")}
            className="flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 transition-colors flex-shrink-0"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Dashboard
          </button>
          <span className="h-3.5 w-px bg-slate-200 flex-shrink-0" />
          <span className="text-sm font-semibold text-slate-700 truncate">{project.title || "Untitled Project"}</span>
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium flex-shrink-0 ${projectBadge.className}`}>
            <span className="h-1.5 w-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: projectBadge.dot }} />
            {projectBadge.label}
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {readyCount > 0 && (
            <button
              onClick={handleDownloadAll}
              disabled={isDownloadingAll}
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 hover:border-blue-200 hover:text-blue-700 disabled:opacity-50 transition-all"
            >
              <DownloadIcon />
              {isDownloadingAll ? "Saving…" : `Save all to hosting (${readyCount})`}
            </button>
          )}
          {(projectStatus === "error" || (isProcessingUpload && !pipelineRunning)) && (
            <button
              onClick={handleRetryProcessing}
              disabled={isRetrying}
              className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-500/20 disabled:opacity-50 transition-all"
            >
              {isRetrying ? "Retrying…" : isProcessingUpload ? "Resume processing" : "Retry processing"}
            </button>
          )}
          {canGenerate && (
            <button
              onClick={() => handleGenerateClips(SEGMENT_60_SEC)}
              disabled={isGenerating}
              className="rounded-lg border border-[#5b6ef5]/30 bg-[#5b6ef5]/10 px-3 py-1.5 text-xs font-semibold text-[#5b6ef5] hover:bg-[#5b6ef5]/20 disabled:opacity-50 transition-all"
            >
              {isGenerating ? "Generating…" : "Split into 60s clips"}
            </button>
          )}
          <button
            onClick={() => router.push(`/project/${projectId}/editor`)}
            className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-[#5b6ef5] to-[#8b5cf6] px-4 py-1.5 text-xs font-semibold text-white shadow-lg shadow-[#5b6ef5]/20 hover:opacity-90 transition-all"
          >
            <EditIcon />
            Open Editor
          </button>
        </div>
      </header>

      {/* ── MAIN ── */}
      <main className="mx-auto max-w-7xl px-6 py-8">

        {/* Page title row */}
        <div className="mb-8 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Clips</h1>
            <p className="mt-1 text-sm text-slate-600">
              {isProcessingUpload
                ? (processingStep || (pipelineRunning
                    ? "Processing your video — 60-second clips will appear here automatically…"
                    : "This job stopped. Resume processing, or upload the video again if the file was lost."))
                : clips.length === 0
                ? "Upload complete — split the full video into 60-second clips"
                : `${clips.length} clip${clips.length !== 1 ? "s" : ""} · ${readyCount} ready${errorCount ? ` · ${errorCount} error` : ""}`}
            </p>
          </div>
          {/* Stats pills */}
          {clips.length > 0 && (
            <div className="flex items-center gap-2">
              <div className="rounded-xl border border-slate-200/70 bg-white px-4 py-2 text-center">
                <p className="text-[10px] text-slate-500 uppercase font-semibold tracking-wide">Total</p>
                <p className="text-xl font-black text-blue-600">{clips.length}</p>
              </div>
              <div className="rounded-xl border border-slate-200/70 bg-white px-4 py-2 text-center">
                <p className="text-[10px] text-slate-500 uppercase font-semibold tracking-wide">Ready</p>
                <p className="text-xl font-black text-emerald-500">{readyCount}</p>
              </div>
            </div>
          )}
        </div>

        {readyCount > 0 && (
          <div className="mb-6 rounded-xl border border-slate-200/70 bg-white px-4 py-4">
            <h2 className="text-sm font-semibold text-slate-900">Ready to publish</h2>
            <p className="mt-1 text-[11px] text-slate-500">
              Instagram captions are pulled from the copy pool on the Publish page.
            </p>
            <button
              onClick={() => router.push(`/project/${projectId}/publish`)}
              className="mt-3 text-xs font-semibold text-[#5b6ef5] hover:underline"
            >
              Publish clips to Instagram →
            </button>
          </div>
        )}

        {processingError && (
          <div className="mb-6 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3">
            <p className="text-sm text-red-700">{processingError}</p>
          </div>
        )}

        {needsRefetch && (
          <div className="mb-6 flex items-center justify-between gap-3 rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3">
            <p className="text-sm text-amber-800">
              {projectStatus === "downloading" || isRefetchingSource
                ? "Re-downloading source video and rebuilding clip files…"
                : "Clip files are missing on the server (temp storage was cleared). Re-fetch the source video before saving to hosting."}
            </p>
            {projectStatus !== "downloading" && (
              <button
                onClick={handleRefetchSource}
                disabled={isRefetchingSource}
                className="flex-shrink-0 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
              >
                {isRefetchingSource ? "Refetching…" : "Refetch source"}
              </button>
            )}
          </div>
        )}

        {canRestoreUpload && (
          <div className="mb-6 flex items-center justify-between gap-3 rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3">
            <p className="text-sm text-amber-800">
              {projectStatus === "downloading" || isRefetchingSource
                ? "Restoring uploaded video from Cloudinary and rebuilding clips…"
                : "Clip files are missing on the server. Restore from Cloudinary backup."}
            </p>
            {projectStatus !== "downloading" && (
              <button
                onClick={handleRefetchSource}
                disabled={isRefetchingSource}
                className="flex-shrink-0 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
              >
                {isRefetchingSource ? "Restoring…" : "Restore from Cloudinary"}
              </button>
            )}
          </div>
        )}

        {needsReupload && (
          <div className="mb-6 rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3">
            <p className="text-sm text-amber-800">
              This was a manual upload and the original file is gone from the server (Render temp storage).
              Clips cannot play until you upload the video again from the dashboard.
            </p>
            <button
              onClick={() => router.push("/dashboard")}
              className="mt-3 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700"
            >
              Go to Dashboard to re-upload
            </button>
          </div>
        )}

        {saveNotice && (
          <div className="mb-6 flex items-start justify-between gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3">
            <p className="text-sm text-emerald-800 break-all">{saveNotice}</p>
            <button
              onClick={() => setSaveNotice(null)}
              className="text-emerald-700/60 hover:text-emerald-800 text-lg leading-none flex-shrink-0"
            >
              ✕
            </button>
          </div>
        )}

        {errorCount > 0 && canGenerate && (
          <div className="mb-6 flex items-center justify-between rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3">
            <p className="text-sm text-amber-700">
              {errorCount} clip{errorCount !== 1 ? "s" : ""} failed earlier. Click &quot;Split into 60s clips&quot; to regenerate them.
            </p>
            <button
              onClick={() => handleGenerateClips(SEGMENT_60_SEC)}
              disabled={isGenerating}
              className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
            >
              Regenerate
            </button>
          </div>
        )}

        {error && (
          <div className="mb-6 flex items-center justify-between gap-3 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3">
            <p className="text-sm text-red-400">{error}</p>
            <div className="flex items-center gap-2 flex-shrink-0">
              {needsRefetch && /missing|not available|refetch/i.test(error) && (
                <button
                  onClick={handleRefetchSource}
                  disabled={isRefetchingSource || projectStatus === "downloading"}
                  className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                >
                  {isRefetchingSource ? "Refetching…" : "Refetch source"}
                </button>
              )}
              <button onClick={() => setError(null)} className="text-red-400/60 hover:text-red-400 text-lg leading-none">✕</button>
            </div>
          </div>
        )}

        {/* ── EMPTY STATE ── */}
        {clips.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200/70 bg-white py-24 text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-100">
              <svg className="h-7 w-7 text-[#5b6ef5]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
              </svg>
            </div>
            <p className="text-sm font-medium text-[#6b6e84]">No clips yet</p>
            <p className="mt-1 text-xs text-[#3a3d52]">
              {projectStatus === "error"
                ? "Fix the error above, then retry or upload again"
                : isProcessingUpload && pipelineRunning
                  ? (processingStep || "Video is processing. 60-second clips will appear here automatically.")
                  : isProcessingUpload
                    ? "Processing stopped. Click Resume, or re-upload from the dashboard if the file was lost."
                    : "Clips are created automatically after upload, or click below to split again"}
            </p>
            {(projectStatus === "error" || (isProcessingUpload && !pipelineRunning)) && (
              <button
                onClick={handleRetryProcessing}
                disabled={isRetrying}
                className="mt-5 flex items-center gap-1.5 rounded-lg border border-red-500/30 bg-red-500/10 px-5 py-2 text-xs font-semibold text-red-600 hover:bg-red-500/20 disabled:opacity-50 transition-all"
              >
                {isRetrying ? "Retrying…" : isProcessingUpload ? "Resume processing" : "Retry processing"}
              </button>
            )}
            {canGenerate && (
              <button
                onClick={() => handleGenerateClips(SEGMENT_60_SEC)}
                disabled={isGenerating}
                className="mt-5 flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-[#5b6ef5] to-[#8b5cf6] px-5 py-2 text-xs font-semibold text-white shadow-lg shadow-blue-300/40 hover:opacity-90 disabled:opacity-50 transition-all"
              >
                {isGenerating ? "Generating…" : "Split into 60s clips"}
              </button>
            )}
          </div>
        ) : (
          /* ── CLIPS GRID ── */
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {sortedClips.map((clip) => {
              const clipId = clip.id || clip._id || ""
              const partNumber = getPartNumber(clip)
              const displayLabel = getClipPartLabel(clip, partNumber)
              const badge = statusBadge(clip.status || "pending")
              const isHovered = hoveredCard === clipId
              const isReady = (clip.status || "").toLowerCase() === "ready"
              const thumbUrl = clipThumbnailUrl(projectId, clipId, token, clip.thumbnail_url)
              const previewUrl = clip.cloudinary_clip_url || (isReady ? clipStreamUrl(projectId, clipId, token) : null)

              return (
                <article
                  key={clipId}
                  onClick={() => setSelectedClip(clip)}
                  onMouseEnter={() => setHoveredCard(clipId)}
                  onMouseLeave={() => setHoveredCard(null)}
                  className="group cursor-pointer rounded-xl border border-slate-200/70 bg-white overflow-hidden transition-all duration-200 hover:border-blue-300/60 hover:shadow-[0_0_24px_rgba(59,130,246,0.12)]"
                >
                  {/* Thumbnail */}
                  <div className="relative aspect-video bg-slate-100 overflow-hidden">
                    {isReady && previewUrl ? (
                      <video
                        preload="metadata"
                        poster={thumbUrl || undefined}
                        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.04]"
                        src={previewUrl}
                        muted
                      />
                    ) : thumbUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={thumbUrl}
                        alt={displayLabel}
                        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.04]"
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center">
                        <svg className="h-10 w-10 text-[#2a2d3e]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                        </svg>
                      </div>
                    )}

                    {/* Part label bar (like reels) */}
                    <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-pink-600/95 via-pink-500/85 to-transparent pt-6 pb-2">
                      <p className="text-center text-sm font-bold tracking-wide text-white drop-shadow">
                        {displayLabel}
                      </p>
                    </div>

                    {/* Duration badge */}
                    <div className="absolute bottom-10 right-2 rounded-md bg-black/60 px-1.5 py-0.5 text-[11px] font-mono text-white backdrop-blur-sm">
                      {formatDuration(clip.duration)}
                    </div>

                    {/* Hover overlay with play button */}
                    <div className={`absolute inset-0 flex items-center justify-center bg-slate-100/80 backdrop-blur-[1px] transition-opacity duration-200 ${isHovered ? "opacity-100" : "opacity-0"}`}>
                      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white shadow-xl">
                        <span className="text-[#191b23] ml-0.5">
                          <PlayIcon />
                        </span>
                      </div>
                    </div>

                    {/* Processing overlay */}
                    {!isReady && (clip.status || "").toLowerCase() === "processing" && (
                      <div className="absolute inset-0 flex items-center justify-center bg-slate-100/70">
                        <div className="text-center">
                          <div className="mx-auto mb-2 h-6 w-6 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
                          <p className="text-[10px] text-slate-500">Processing</p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Card info */}
                  <div className="p-3">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-sm font-medium text-slate-800 truncate leading-tight">
                        {displayLabel}
                      </h3>
                      {isReady && (
                        <button
                          type="button"
                          title="Save clip to hosting"
                          onClick={(e) => handleDownloadClip(clip, partNumber, e)}
                          disabled={downloadingClipId === clipId}
                          className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-600 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 disabled:opacity-50 transition-all"
                        >
                          <DownloadIcon />
                        </button>
                      )}
                    </div>

                    <div className="mt-2 flex items-center justify-between">
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${badge.className}`}>
                        <span className="h-1.5 w-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: badge.dot }} />
                        {badge.label}
                      </span>
                      <div className="flex items-center gap-2 text-[11px] font-mono text-[#3a3d52]">
                        <span>{formatTime(clip.start_time)}</span>
                        <span className="text-slate-500">→</span>
                        <span>{formatTime(clip.end_time)}</span>
                      </div>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </main>

      {/* ── CLIP MODAL ── */}
      {selectedClip && (
        <ClipModal
          clip={selectedClip}
          projectId={projectId}
          token={token}
          displayLabel={getClipPartLabel(selectedClip, getPartNumber(selectedClip))}
          onClose={() => setSelectedClip(null)}
          onDelete={handleClipDeleted}
          onSavedRemote={(url) => {
            setSaveNotice(`Saved to hosting: ${url}`)
            setSelectedClip(null)
          }}
        />
      )}
    </div>
  )
}