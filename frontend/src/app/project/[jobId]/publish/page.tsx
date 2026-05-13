"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import api from "@/lib/api"

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

type PublishTarget = "youtube" | "instagram"

type PublishStatus = {
  clipId: string
  target: PublishTarget
  status: "idle" | "publishing" | "success" | "error"
  message?: string
  timestamp?: string
}

type ConnectedAccount = {
  youtube: boolean
  instagram: boolean
}

function formatDuration(totalSeconds?: number | null) {
  if (!totalSeconds || totalSeconds < 1) return "--:--"
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = Math.floor(totalSeconds % 60)
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`
}

function formatTimestamp(iso?: string) {
  if (!iso) return ""
  const d = new Date(iso)
  return d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })
}

const PLATFORMS = [
  {
    key: "youtube" as PublishTarget,
    label: "YouTube Shorts",
    shortLabel: "YouTube",
    description: "Vertical short-form videos up to 60s",
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
      </svg>
    ),
    color: "text-red-500",
    ringColor: "ring-red-200",
    activeBorder: "border-red-400",
    activeBg: "bg-red-50",
    badge: "bg-red-100 text-red-700",
    connectBg: "bg-red-600 hover:bg-red-700",
  },
  {
    key: "instagram" as PublishTarget,
    label: "Instagram Reels",
    shortLabel: "Instagram",
    description: "Reels up to 90 seconds with effects",
    icon: (
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 0 0 0-12.324zM12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.406-11.845a1.44 1.44 0 1 0 0 2.881 1.44 1.44 0 0 0 0-2.881z" />
      </svg>
    ),
    color: "text-pink-500",
    ringColor: "ring-pink-200",
    activeBorder: "border-pink-400",
    activeBg: "bg-pink-50",
    badge: "bg-pink-100 text-pink-700",
    connectBg: "bg-gradient-to-r from-pink-500 to-purple-600 hover:from-pink-600 hover:to-purple-700",
  },
]

export default function PublishPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.jobId as string

  const [clips, setClips] = useState<ClipData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedClipId, setSelectedClipId] = useState<string>("")
  const [selectedPlatform, setSelectedPlatform] = useState<PublishTarget>("youtube")
  const [publishTitle, setPublishTitle] = useState("")
  const [publishDescription, setPublishDescription] = useState("")
  const [publishStatuses, setPublishStatuses] = useState<PublishStatus[]>([])
  const [connectedAccounts, setConnectedAccounts] = useState<ConnectedAccount>({
    youtube: false,
    instagram: false,
  })
  const [connectingPlatform, setConnectingPlatform] = useState<PublishTarget | null>(null)
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" | "info" } | null>(null)
  const [activeTab, setActiveTab] = useState<"publish" | "history">("publish")

  const showToast = (message: string, type: "success" | "error" | "info" = "info") => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3500)
  }

  const loadClips = useCallback(async () => {
    try {
      const response = await api.get(`/api/v1/projects/${projectId}/clips`)
      const clipsData = Array.isArray(response.data) ? response.data : []
      setClips(clipsData)
      if (clipsData.length > 0) {
        setSelectedClipId(clipsData[0].id || clipsData[0]._id || "")
      }
    } catch {
      setError("Could not load clips.")
    } finally {
      setLoading(false)
    }
  }, [projectId])

  // Load connected account status from localStorage (persists across sessions)
  useEffect(() => {
    const saved = localStorage.getItem("connectedAccounts")
    if (saved) {
      try {
        setConnectedAccounts(JSON.parse(saved))
      } catch {
        // ignore
      }
    }
  }, [])

  useEffect(() => {
    const token = localStorage.getItem("token")
    if (!token) {
      router.push("/login")
      return
    }
    loadClips()
  }, [loadClips, router])

  const handleConnectAccount = async (platform: PublishTarget) => {
    setConnectingPlatform(platform)
    try {
      // Try to get OAuth URL from backend
      const response = await api.get(`/api/v1/auth/oauth/${platform}`)
      if (response.data?.auth_url) {
        window.open(response.data.auth_url, "_blank", "width=600,height=700")
        showToast(`Opening ${platform} login — complete it in the new window.`, "info")
        // Optimistically mark as connected; real apps would verify via callback
        setTimeout(() => {
          const updated = { ...connectedAccounts, [platform]: true }
          setConnectedAccounts(updated)
          localStorage.setItem("connectedAccounts", JSON.stringify(updated))
          showToast(`${platform === "youtube" ? "YouTube" : "Instagram"} connected! ✓`, "success")
        }, 3000)
      }
    } catch {
      // Backend OAuth not ready yet — show Coming Soon message
      showToast(`${platform === "youtube" ? "YouTube" : "Instagram"} OAuth is coming soon. Backend integration pending.`, "info")
    } finally {
      setConnectingPlatform(null)
    }
  }

  const handleDisconnect = (platform: PublishTarget) => {
    const updated = { ...connectedAccounts, [platform]: false }
    setConnectedAccounts(updated)
    localStorage.setItem("connectedAccounts", JSON.stringify(updated))
    showToast(`${platform === "youtube" ? "YouTube" : "Instagram"} disconnected.`, "info")
  }

  const getPublishStatus = (clipId: string, target: PublishTarget) =>
    publishStatuses.find((s) => s.clipId === clipId && s.target === target)

  const handlePublish = async () => {
    if (!selectedClipId || !publishTitle.trim()) return

    const platform = PLATFORMS.find((p) => p.key === selectedPlatform)!

    if (!connectedAccounts[selectedPlatform]) {
      showToast(`Connect your ${platform.shortLabel} account first.`, "error")
      return
    }

    setPublishStatuses((prev) => [
      ...prev.filter((s) => !(s.clipId === selectedClipId && s.target === selectedPlatform)),
      { clipId: selectedClipId, target: selectedPlatform, status: "publishing" },
    ])

    try {
      await api.post(`/api/v1/projects/${projectId}/publish`, {
        clip_id: selectedClipId,
        platform: selectedPlatform,
        title: publishTitle.trim(),
        description: publishDescription.trim(),
      })

      const now = new Date().toISOString()
      setPublishStatuses((prev) => [
        ...prev.filter((s) => !(s.clipId === selectedClipId && s.target === selectedPlatform)),
        {
          clipId: selectedClipId,
          target: selectedPlatform,
          status: "success",
          message: `Published to ${platform.label} successfully!`,
          timestamp: now,
        },
      ])
      showToast(`Published to ${platform.label}! ✓`, "success")
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      const now = new Date().toISOString()
      setPublishStatuses((prev) => [
        ...prev.filter((s) => !(s.clipId === selectedClipId && s.target === selectedPlatform)),
        {
          clipId: selectedClipId,
          target: selectedPlatform,
          status: "error",
          message: detail || "Publish failed. Please try again.",
          timestamp: now,
        },
      ])
      showToast(detail || "Publish failed. Please try again.", "error")
    }
  }

  const selectedClip = clips.find((c) => (c.id || c._id) === selectedClipId)
  const currentStatus = getPublishStatus(selectedClipId, selectedPlatform)
  const isPublishing = currentStatus?.status === "publishing"

  // All publish history (success + error)
  const publishHistory = publishStatuses.filter((s) => s.status === "success" || s.status === "error")

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#faf8ff]">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#004ac6]/20 border-t-[#004ac6]" />
          <p className="text-sm text-[#737686]">Loading clips…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#faf8ff] text-[#191b23]">
      {/* Header */}
      <header className="sticky top-0 z-40 flex h-12 items-center justify-between border-b border-[#e1e2ed] bg-white/70 px-4 shadow-[0_2px_10px_-3px_rgba(0,0,0,0.07)] backdrop-blur-xl">
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.push(`/project/${projectId}/clips`)}
            className="text-sm font-medium text-[#004ac6] hover:underline"
          >
            ← Back to Clips
          </button>
          <span className="text-sm text-[#c3c6d7]">|</span>
          <span className="text-sm font-bold">Publish</span>
        </div>
        {/* Tabs */}
        <div className="flex items-center gap-1 rounded-lg bg-[#f0f1f9] p-1">
          <button
            onClick={() => setActiveTab("publish")}
            className={`rounded-md px-3 py-1 text-xs font-medium transition-all ${
              activeTab === "publish" ? "bg-white shadow-sm text-[#191b23]" : "text-[#737686] hover:text-[#191b23]"
            }`}
          >
            Publish
          </button>
          <button
            onClick={() => setActiveTab("history")}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-all ${
              activeTab === "history" ? "bg-white shadow-sm text-[#191b23]" : "text-[#737686] hover:text-[#191b23]"
            }`}
          >
            History
            {publishHistory.length > 0 && (
              <span className="rounded-full bg-[#004ac6] px-1.5 py-0.5 text-[9px] text-white">
                {publishHistory.length}
              </span>
            )}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8">

        {/* ─── PUBLISH TAB ─── */}
        {activeTab === "publish" && (
          <>
            <div className="mb-6">
              <h1 className="text-2xl font-bold">Publish Clips</h1>
              <p className="mt-1 text-sm text-[#434655]">
                Connect your accounts, pick a clip, and publish directly to YouTube Shorts or Instagram Reels.
              </p>
            </div>

            {error && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

            {/* ── Connected Accounts Banner ── */}
            <section className="mb-6 rounded-xl border border-[#e1e2ed] bg-white p-5 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold">Connected Accounts</h2>
                <span className="rounded-full bg-[#f0f1f9] px-2 py-0.5 text-[10px] text-[#737686]">
                  {Object.values(connectedAccounts).filter(Boolean).length} / 2 connected
                </span>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {PLATFORMS.map((platform) => {
                  const isConnected = connectedAccounts[platform.key]
                  const isConnecting = connectingPlatform === platform.key
                  return (
                    <div
                      key={platform.key}
                      className={`flex items-center justify-between rounded-xl border p-4 transition-all ${
                        isConnected ? "border-emerald-200 bg-emerald-50" : "border-[#e1e2ed] bg-[#faf8ff]"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className={platform.color}>{platform.icon}</span>
                        <div>
                          <p className="text-sm font-medium">{platform.label}</p>
                          <p className="text-[11px] text-[#737686]">{platform.description}</p>
                        </div>
                      </div>
                      {isConnected ? (
                        <div className="flex items-center gap-2">
                          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
                            ✓ Connected
                          </span>
                          <button
                            onClick={() => handleDisconnect(platform.key)}
                            className="rounded-md border border-[#e1e2ed] px-2 py-1 text-[10px] text-[#737686] hover:border-red-300 hover:text-red-600 transition-colors"
                          >
                            Disconnect
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => handleConnectAccount(platform.key)}
                          disabled={isConnecting}
                          className={`rounded-lg px-3 py-1.5 text-xs font-medium text-white transition-all disabled:opacity-60 ${platform.connectBg}`}
                        >
                          {isConnecting ? (
                            <span className="flex items-center gap-1.5">
                              <span className="h-3 w-3 animate-spin rounded-full border border-white/30 border-t-white" />
                              Connecting…
                            </span>
                          ) : (
                            "Connect"
                          )}
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
              <p className="mt-3 text-[11px] text-[#737686]">
                ⚠️ OAuth integration is pending backend setup. Connecting will open the auth window once the backend is ready.
              </p>
            </section>

            {clips.length === 0 ? (
              <div className="rounded-xl border border-dashed border-[#c3c6d7] bg-white p-10 text-center">
                <p className="text-sm text-[#737686]">No clips available to publish yet.</p>
                <button
                  onClick={() => router.push(`/project/${projectId}/clips`)}
                  className="mt-4 text-sm font-medium text-[#004ac6] underline"
                >
                  Go back to clips
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_1.2fr]">

                {/* Left — Clip selector */}
                <section>
                  <h2 className="mb-3 text-base font-semibold">Select a Clip</h2>
                  <div className="space-y-3">
                    {clips.map((clip) => {
                      const clipId = clip.id || clip._id || ""
                      const isSelected = clipId === selectedClipId
                      const ytStatus = getPublishStatus(clipId, "youtube")
                      const igStatus = getPublishStatus(clipId, "instagram")

                      return (
                        <button
                          key={clipId}
                          type="button"
                          onClick={() => setSelectedClipId(clipId)}
                          className={`w-full rounded-xl border p-3 text-left transition-all ${
                            isSelected
                              ? "border-[#004ac6] bg-white shadow-md ring-2 ring-[#004ac6]/20"
                              : "border-[#e1e2ed] bg-white hover:border-[#004ac6]/40 hover:shadow-sm"
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            {/* Thumbnail */}
                            <div className="relative h-14 w-24 flex-shrink-0 overflow-hidden rounded-lg bg-[#ededf9]">
                              {clip.thumbnail_url ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img
                                  src={clip.thumbnail_url}
                                  alt={clip.label || "Clip"}
                                  className="h-full w-full object-cover"
                                />
                              ) : (
                                <div className="flex h-full items-center justify-center text-[10px] text-[#737686]">
                                  No preview
                                </div>
                              )}
                              <div className="absolute bottom-1 right-1 rounded bg-black/70 px-1 py-0.5 text-[9px] text-white">
                                {formatDuration(clip.duration)}
                              </div>
                            </div>

                            {/* Info */}
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-medium">
                                {clip.label || `Clip ${formatDuration(clip.start_time)} – ${formatDuration(clip.end_time)}`}
                              </p>
                              <div className="mt-1.5 flex flex-wrap gap-1.5">
                                {ytStatus?.status === "success" && (
                                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
                                    ✓ YouTube
                                  </span>
                                )}
                                {igStatus?.status === "success" && (
                                  <span className="rounded-full bg-pink-100 px-2 py-0.5 text-[10px] font-semibold text-pink-700">
                                    ✓ Instagram
                                  </span>
                                )}
                                {ytStatus?.status === "error" && (
                                  <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold text-red-700">
                                    ✗ YouTube failed
                                  </span>
                                )}
                                {igStatus?.status === "error" && (
                                  <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold text-red-700">
                                    ✗ Instagram failed
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                </section>

                {/* Right — Publish form */}
                <section className="rounded-xl border border-[#e1e2ed] bg-white p-6 shadow-sm">
                  <h2 className="mb-4 text-base font-semibold">Publish Settings</h2>

                  {/* Platform selector */}
                  <div className="mb-5">
                    <p className="mb-2 text-xs font-medium uppercase text-[#737686]">Platform</p>
                    <div className="grid grid-cols-2 gap-3">
                      {PLATFORMS.map((platform) => {
                        const isActive = selectedPlatform === platform.key
                        const isConnected = connectedAccounts[platform.key]
                        return (
                          <button
                            key={platform.key}
                            type="button"
                            onClick={() => setSelectedPlatform(platform.key)}
                            className={`relative flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-medium transition-all ${
                              isActive
                                ? `${platform.activeBg} ${platform.activeBorder} ${platform.color} ring-2 ${platform.ringColor}`
                                : "border-[#e1e2ed] text-[#737686] hover:border-[#c3c6d7]"
                            }`}
                          >
                            <span className={isActive ? platform.color : "text-[#737686]"}>
                              {platform.icon}
                            </span>
                            {platform.shortLabel}
                            {isConnected && (
                              <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-emerald-400" />
                            )}
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  {/* Not connected warning */}
                  {!connectedAccounts[selectedPlatform] && (
                    <div className="mb-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-700">
                      <svg className="h-4 w-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      {`Connect your ${PLATFORMS.find(p => p.key === selectedPlatform)?.shortLabel} account above to publish.`}
                    </div>
                  )}

                  {/* Selected clip preview */}
                  {selectedClip && (
                    <div className="mb-5 flex items-center gap-3 rounded-lg bg-[#faf8ff] p-3">
                      <div className="h-10 w-16 flex-shrink-0 overflow-hidden rounded bg-[#ededf9]">
                        {selectedClip.thumbnail_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={selectedClip.thumbnail_url}
                            alt="Selected clip"
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <div className="flex h-full items-center justify-center text-[9px] text-[#737686]">
                            No preview
                          </div>
                        )}
                      </div>
                      <div>
                        <p className="text-xs font-medium text-[#191b23]">
                          {selectedClip.label ||
                            `Clip ${formatDuration(selectedClip.start_time)} – ${formatDuration(selectedClip.end_time)}`}
                        </p>
                        <p className="text-[11px] text-[#737686]">{formatDuration(selectedClip.duration)}</p>
                      </div>
                    </div>
                  )}

                  {/* Title */}
                  <div className="mb-4">
                    <label className="mb-1.5 block text-xs font-medium uppercase text-[#737686]">
                      Title <span className="text-red-500">*</span>
                    </label>
                    <input
                      value={publishTitle}
                      onChange={(e) => setPublishTitle(e.target.value)}
                      placeholder="Enter a catchy title..."
                      maxLength={100}
                      className="w-full rounded-lg border border-[#d4d7e8] px-3 py-2 text-sm outline-none transition-colors focus:border-[#004ac6]"
                    />
                    <p className="mt-1 text-right text-[10px] text-[#b0b3c6]">{publishTitle.length}/100</p>
                  </div>

                  {/* Description */}
                  <div className="mb-6">
                    <label className="mb-1.5 block text-xs font-medium uppercase text-[#737686]">
                      Description
                    </label>
                    <textarea
                      value={publishDescription}
                      onChange={(e) => setPublishDescription(e.target.value)}
                      rows={3}
                      maxLength={500}
                      placeholder="Add a description, hashtags..."
                      className="w-full rounded-lg border border-[#d4d7e8] px-3 py-2 text-sm outline-none transition-colors focus:border-[#004ac6]"
                    />
                    <p className="mt-1 text-right text-[10px] text-[#b0b3c6]">{publishDescription.length}/500</p>
                  </div>

                  {/* Publish button */}
                  <button
                    type="button"
                    onClick={handlePublish}
                    disabled={isPublishing || !selectedClipId || !publishTitle.trim()}
                    className="w-full rounded-lg bg-gradient-to-r from-[#004ac6] to-[#712ae2] py-2.5 text-sm font-medium text-white shadow-[0_4px_14px_0_rgba(0,74,198,0.39)] hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60 transition-opacity"
                  >
                    {isPublishing ? (
                      <span className="flex items-center justify-center gap-2">
                        <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                        Publishing...
                      </span>
                    ) : (
                      `Publish to ${PLATFORMS.find((p) => p.key === selectedPlatform)?.label}`
                    )}
                  </button>

                  {currentStatus?.status === "success" && (
                    <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                      ✓ {currentStatus.message}
                    </div>
                  )}
                  {currentStatus?.status === "error" && (
                    <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                      ✗ {currentStatus.message}
                    </div>
                  )}
                </section>
              </div>
            )}
          </>
        )}

        {/* ─── HISTORY TAB ─── */}
        {activeTab === "history" && (
          <>
            <div className="mb-6">
              <h1 className="text-2xl font-bold">Publish History</h1>
              <p className="mt-1 text-sm text-[#434655]">
                All your past publish attempts for this project.
              </p>
            </div>

            {publishHistory.length === 0 ? (
              <div className="rounded-xl border border-dashed border-[#c3c6d7] bg-white p-12 text-center">
                <div className="mb-3 text-3xl">📭</div>
                <p className="text-sm font-medium text-[#737686]">No publish history yet.</p>
                <p className="mt-1 text-xs text-[#b0b3c6]">Published clips will appear here.</p>
                <button
                  onClick={() => setActiveTab("publish")}
                  className="mt-4 rounded-lg bg-[#004ac6] px-4 py-2 text-sm font-medium text-white hover:bg-[#003aa0]"
                >
                  Publish a clip
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {[...publishHistory].reverse().map((record, i) => {
                  const clip = clips.find((c) => (c.id || c._id) === record.clipId)
                  const platform = PLATFORMS.find((p) => p.key === record.target)!
                  return (
                    <div
                      key={i}
                      className={`flex items-center gap-4 rounded-xl border bg-white p-4 shadow-sm ${
                        record.status === "success" ? "border-emerald-100" : "border-red-100"
                      }`}
                    >
                      {/* Thumbnail */}
                      <div className="h-12 w-20 flex-shrink-0 overflow-hidden rounded-lg bg-[#ededf9]">
                        {clip?.thumbnail_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={clip.thumbnail_url}
                            alt="clip"
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <div className="flex h-full items-center justify-center text-[9px] text-[#737686]">
                            No preview
                          </div>
                        )}
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <p className="truncate text-sm font-medium">
                          {clip?.label || `Clip ${formatDuration(clip?.start_time)} – ${formatDuration(clip?.end_time)}`}
                        </p>
                        <div className="mt-1 flex items-center gap-2">
                          <span className={`flex items-center gap-1 text-xs ${platform.color}`}>
                            {platform.icon}
                            {platform.label}
                          </span>
                          <span className="text-[#c3c6d7]">·</span>
                          <span className="text-[11px] text-[#737686]">{formatTimestamp(record.timestamp)}</span>
                        </div>
                      </div>

                      {/* Status badge */}
                      <div className="flex-shrink-0">
                        {record.status === "success" ? (
                          <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
                            ✓ Published
                          </span>
                        ) : (
                          <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-700">
                            ✗ Failed
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}
      </main>

      {/* Toast */}
      {toast && (
        <div
          className={`fixed bottom-6 left-1/2 z-[200] -translate-x-1/2 rounded-xl px-5 py-3 text-sm font-medium text-white shadow-lg transition-all ${
            toast.type === "success"
              ? "bg-emerald-600"
              : toast.type === "error"
              ? "bg-red-600"
              : "bg-[#191b23]"
          }`}
        >
          {toast.message}
        </div>
      )}
    </div>
  )
}