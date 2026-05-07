"use client"

import { FormEvent, useCallback, useEffect, useState } from "react"
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

type AssetResult = {
  source_id: string
  source: "pexels" | "pixabay"
  asset_type: "image" | "video"
  url: string
  thumbnail_url?: string | null
  photographer?: string | null
}

type SavedAsset = {
  id?: string
  _id?: string
  source?: "pexels" | "pixabay"
  asset_type?: "image" | "video"
  url?: string
  thumbnail_url?: string | null
  photographer?: string | null
}

type CaptionItem = {
  id?: string
  _id?: string
  clip_id?: string | null
  raw_text?: string
  created_at?: string
  updated_at?: string
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
  const [searchQuery, setSearchQuery] = useState("")
  const [searchSource, setSearchSource] = useState<"all" | "pexels" | "pixabay">("all")
  const [searchResults, setSearchResults] = useState<AssetResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [savingAssetId, setSavingAssetId] = useState<string | null>(null)
  const [savedAssets, setSavedAssets] = useState<SavedAsset[]>([])
  const [showGallery, setShowGallery] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [isSelectMode, setIsSelectMode] = useState(false)
  const [selectedAssetIds, setSelectedAssetIds] = useState<Set<string>>(new Set())
  const [isDeletingSelected, setIsDeletingSelected] = useState(false)
  const [captions, setCaptions] = useState<CaptionItem[]>([])
  const [selectedCaptionClipId, setSelectedCaptionClipId] = useState<string>("")
  const [captionText, setCaptionText] = useState("")
  const [isSavingCaption, setIsSavingCaption] = useState(false)

  const loadSavedAssets = useCallback(async () => {
    try {
      const response = await api.get(`/api/v1/projects/${projectId}/assets`)
      setSavedAssets(Array.isArray(response.data) ? response.data : [])
    } catch {
      // non-blocking for page load
    }
  }, [projectId])

  const loadCaptions = useCallback(async () => {
    try {
      const response = await api.get(`/api/v1/projects/${projectId}/captions`)
      setCaptions(Array.isArray(response.data) ? response.data : [])
    } catch {
      // non-blocking
    }
  }, [projectId])

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
    loadSavedAssets()
    loadCaptions()
  }, [loadProject, loadSavedAssets, loadCaptions, router])

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

  const handleSearchAssets = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!searchQuery.trim()) return
    setIsSearching(true)
    setError(null)
    try {
      const response = await api.get("/api/v1/assets/search", {
        params: { q: searchQuery.trim(), type: "image", source: searchSource, per_page: 18 },
      })
      setSearchResults(Array.isArray(response.data?.results) ? response.data.results : [])
    } catch {
      setError("Could not search assets from Pixabay/Pexels.")
    } finally {
      setIsSearching(false)
    }
  }

  const handleSaveAsset = async (asset: AssetResult) => {
    setSavingAssetId(asset.source_id)
    setError(null)
    setSaveMessage(null)
    try {
      const response = await api.post(`/api/v1/projects/${projectId}/assets`, {
        source_id: asset.source_id,
        source: asset.source,
        asset_type: asset.asset_type,
        url: asset.url,
        thumbnail_url: asset.thumbnail_url,
        query_used: searchQuery.trim(),
        photographer: asset.photographer,
      })
      setSaveMessage("Saved to project gallery.")
      const saved = response.data as SavedAsset
      setSavedAssets((prev) => [saved, ...prev])
      setShowGallery(true)
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      if (status === 409) {
        window.alert(detail || "This image is already saved in the gallery.")
      } else {
        setError(detail || "Could not save selected asset.")
      }
    } finally {
      setSavingAssetId(null)
    }
  }

  const toggleAssetSelection = (assetId: string) => {
    setSelectedAssetIds((prev) => {
      const next = new Set(prev)
      if (next.has(assetId)) next.delete(assetId)
      else next.add(assetId)
      return next
    })
  }

  const handleDeleteSelectedAssets = async () => {
    if (selectedAssetIds.size === 0 || isDeletingSelected) return
    if (!window.confirm(`Delete ${selectedAssetIds.size} selected image(s) from gallery?`)) return

    setIsDeletingSelected(true)
    setError(null)
    try {
      await Promise.all(Array.from(selectedAssetIds).map((assetId) => api.delete(`/api/v1/assets/${assetId}`)))
      setSavedAssets((prev) => prev.filter((asset) => !selectedAssetIds.has(asset.id || asset._id || "")))
      setSelectedAssetIds(new Set())
      setIsSelectMode(false)
    } catch {
      setError("Could not delete selected images.")
    } finally {
      setIsDeletingSelected(false)
    }
  }

  const handleCaptionFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      setCaptionText(text)
    } catch {
      setError("Could not read caption file.")
    } finally {
      event.target.value = ""
    }
  }

  const handleSaveCaption = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!captionText.trim()) return
    setIsSavingCaption(true)
    setError(null)
    try {
      await api.post(`/api/v1/projects/${projectId}/captions`, {
        raw_text: captionText.trim(),
        clip_id: selectedCaptionClipId || null,
      })
      setCaptionText("")
      await loadCaptions()
    } catch {
      setError("Could not save caption.")
    } finally {
      setIsSavingCaption(false)
    }
  }

  const handleDeleteCaption = async (captionId: string) => {
    setError(null)
    try {
      await api.delete(`/api/v1/captions/${captionId}`)
      await loadCaptions()
    } catch {
      setError("Could not delete caption.")
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
  const isRetryable = st === "error"
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

      <main className="mx-auto max-w-7xl px-6 py-8">
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

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.4fr_1fr]">
          <section>
            <h2 className="mb-4 text-lg font-bold">Clips</h2>
            {clips.length === 0 ? (
              <div className="rounded-xl border border-dashed border-[#c3c6d7] bg-white p-8 text-center text-sm text-[#434655]">
                {st === "ready"
                  ? "No clips yet. Use the editor to create clips from this video."
                  : "Clips will be available once the video download is complete."}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
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

            <div className="mt-6 rounded-xl border border-[#e1e2ed] bg-white p-4">
              <h3 className="mb-1 text-base font-semibold">Caption Box</h3>
              <p className="mb-3 text-xs text-[#5e6172]">Upload or paste captions, then map them to a clip of this project.</p>
              <form onSubmit={handleSaveCaption} className="space-y-3">
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  <select
                    value={selectedCaptionClipId}
                    onChange={(event) => setSelectedCaptionClipId(event.target.value)}
                    className="rounded-lg border border-[#d4d7e8] px-3 py-2 text-sm"
                  >
                    <option value="">Map to whole project</option>
                    {clips.map((clip) => {
                      const clipId = clip.id || clip._id || ""
                      return (
                        <option key={clipId} value={clipId}>
                          {clip.label || `Clip ${formatDuration(clip.start_time)} - ${formatDuration(clip.end_time)}`}
                        </option>
                      )
                    })}
                  </select>
                  <input
                    type="file"
                    accept=".txt,.srt,.vtt"
                    onChange={handleCaptionFileUpload}
                    className="rounded-lg border border-[#d4d7e8] px-3 py-2 text-sm"
                  />
                </div>
                <textarea
                  value={captionText}
                  onChange={(event) => setCaptionText(event.target.value)}
                  rows={5}
                  placeholder="Paste or upload caption text here..."
                  className="w-full rounded-lg border border-[#d4d7e8] px-3 py-2 text-sm outline-none focus:border-[#004ac6]"
                />
                <button
                  type="submit"
                  disabled={isSavingCaption || !captionText.trim()}
                  className="rounded-lg bg-[#004ac6] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {isSavingCaption ? "Saving Caption..." : "Save Caption"}
                </button>
              </form>

              <div className="mt-4 space-y-2">
                {captions.length === 0 ? (
                  <p className="text-xs text-[#6b6f82]">No captions saved yet.</p>
                ) : (
                  captions.map((caption) => {
                    const captionId = caption.id || caption._id || ""
                    return (
                      <div key={captionId} className="rounded-lg border border-[#eceef8] bg-[#fcfcff] p-3">
                        <p className="line-clamp-3 text-sm">{caption.raw_text || ""}</p>
                        <div className="mt-2 flex items-center justify-between text-[11px] text-[#6b6f82]">
                          <span>Clip: {caption.clip_id ? caption.clip_id.slice(-6) : "project"}</span>
                          <button
                            type="button"
                            onClick={() => handleDeleteCaption(captionId)}
                            className="font-medium text-red-600 hover:underline"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          </section>

          <aside className="rounded-xl border border-[#e1e2ed] bg-white p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold">{showGallery ? "Project Gallery" : "Image Search"}</h2>
              <div className="inline-flex overflow-hidden rounded-lg border border-[#d4d7e8] bg-white">
                <button
                  type="button"
                  onClick={() => setShowGallery(false)}
                  className={`px-2.5 py-1 text-xs font-medium ${!showGallery ? "bg-[#191b23] text-white" : "hover:bg-[#f6f7ff]"}`}
                >
                  Search
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowGallery(true)
                    loadSavedAssets()
                  }}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium ${showGallery ? "bg-[#191b23] text-white" : "hover:bg-[#f6f7ff]"}`}
                  title="Open project gallery tab"
                >
                  <span aria-hidden>🖼️</span>
                  <span>Gallery ({savedAssets.length})</span>
                </button>
              </div>
            </div>
            {!showGallery ? (
              <>
                <p className="mb-4 text-xs text-[#5e6172]">Search and save images from Pixabay or Pexels.</p>
                {saveMessage ? <p className="mb-3 text-xs text-emerald-700">{saveMessage}</p> : null}
                <form onSubmit={handleSearchAssets} className="mb-4 space-y-2">
                  <input
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    placeholder="Search images..."
                    className="w-full rounded-lg border border-[#d4d7e8] px-3 py-2 text-sm outline-none focus:border-[#004ac6]"
                  />
                  <div className="flex items-center gap-2">
                    <select
                      value={searchSource}
                      onChange={(event) => setSearchSource(event.target.value as "all" | "pexels" | "pixabay")}
                      className="rounded-lg border border-[#d4d7e8] px-3 py-2 text-sm"
                    >
                      <option value="all">All Sources</option>
                      <option value="pexels">Pexels</option>
                      <option value="pixabay">Pixabay</option>
                    </select>
                    <button
                      type="submit"
                      disabled={isSearching}
                      className="rounded-lg bg-[#191b23] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                    >
                      {isSearching ? "Searching..." : "Search"}
                    </button>
                  </div>
                </form>
                <div className="grid grid-cols-1 gap-3">
                  {searchResults.map((asset) => (
                    <article key={`${asset.source}-${asset.source_id}`} className="overflow-hidden rounded-lg border border-[#eceef8]">
                      <div className="aspect-video bg-[#f2f4ff]">
                        {asset.thumbnail_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={asset.thumbnail_url} alt="Asset thumbnail" className="h-full w-full object-cover" />
                        ) : (
                          <div className="flex h-full items-center justify-center text-xs text-[#6b6f82]">No preview</div>
                        )}
                      </div>
                      <div className="space-y-2 p-3">
                        <p className="text-xs uppercase text-[#6b6f82]">
                          {asset.source} - {asset.asset_type}
                        </p>
                        <button
                          onClick={() => handleSaveAsset(asset)}
                          disabled={savingAssetId === asset.source_id}
                          className="rounded-lg border border-[#d4d7e8] px-3 py-1.5 text-xs hover:bg-[#f6f7ff] disabled:opacity-60"
                        >
                          {savingAssetId === asset.source_id ? "Saving..." : "Save to Project"}
                        </button>
                      </div>
                    </article>
                  ))}
                  {searchResults.length === 0 ? <p className="text-sm text-[#6b6f82]">No results yet. Run a search above.</p> : null}
                </div>
              </>
            ) : (
              <div>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold">Project Gallery</h3>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setIsSelectMode((prev) => !prev)
                        setSelectedAssetIds(new Set())
                      }}
                      className="rounded-lg border border-[#d4d7e8] px-2 py-1 text-[11px] font-medium hover:bg-[#f6f7ff]"
                    >
                      {isSelectMode ? "Cancel Select" : "Select"}
                    </button>
                    {isSelectMode ? (
                      <button
                        type="button"
                        onClick={handleDeleteSelectedAssets}
                        disabled={selectedAssetIds.size === 0 || isDeletingSelected}
                        className="rounded-lg border border-red-200 px-2 py-1 text-[11px] font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                      >
                        {isDeletingSelected ? "Deleting..." : `Delete (${selectedAssetIds.size})`}
                      </button>
                    ) : null}
                  </div>
                </div>
                {savedAssets.length === 0 ? (
                  <p className="text-xs text-[#6b6f82]">No images saved yet.</p>
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    {savedAssets.map((asset) => {
                      const key = asset.id || asset._id || `${asset.source}-${asset.url}`
                      const assetId = asset.id || asset._id || ""
                      const preview = asset.thumbnail_url || asset.url
                      const selected = assetId ? selectedAssetIds.has(assetId) : false
                      return (
                        <button
                          key={key}
                          type="button"
                          onClick={() => {
                            if (isSelectMode && assetId) {
                              toggleAssetSelection(assetId)
                              return
                            }
                            if (asset.url) window.open(asset.url, "_blank", "noopener,noreferrer")
                          }}
                          className={`relative overflow-hidden rounded-lg border bg-white ${selected ? "border-[#004ac6] ring-2 ring-[#004ac6]/30" : "border-[#eceef8]"}`}
                        >
                          <div className="aspect-square bg-[#f2f4ff]">
                            {preview ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={preview} alt="Saved project asset" className="h-full w-full object-cover" />
                            ) : (
                              <div className="flex h-full items-center justify-center text-[11px] text-[#6b6f82]">No preview</div>
                            )}
                          </div>
                          {isSelectMode ? (
                            <span className="absolute right-1 top-1 rounded-full bg-white/90 px-1.5 py-0.5 text-[10px] font-semibold text-[#191b23]">
                              {selected ? "Selected" : "Tap"}
                            </span>
                          ) : null}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            )}
          </aside>
        </div>
      </main>
    </div>
  )
}
