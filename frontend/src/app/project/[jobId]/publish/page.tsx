"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
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
  host_uploads?: Record<string, HostUploadState>
  publish_status?: string | null
  publish_platform?: string | null
  published_url?: string | null
}

type PublishTarget = "youtube" | "instagram"
type HostKey = "krakenfiles" | "uploadrar" | "up4ever"

type HostUploadState = {
  status?: string
  url?: string | null
  file_code?: string | null
  error?: string | null
  updated_at?: string | null
}

type PublishStatus = {
  clipId: string
  target: PublishTarget | HostKey
  status: "idle" | "publishing" | "success" | "error"
  message?: string
  url?: string
  timestamp?: string
}

type ConnectedAccount = {
  youtube: boolean
  instagram: boolean
}

type HostInfo = {
  key: HostKey
  label: string
  configured: boolean
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

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
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
    connectBg: "bg-gradient-to-r from-pink-500 to-purple-600 hover:from-pink-600 hover:to-purple-700",
  },
]

const DEFAULT_HOSTS: HostInfo[] = [
  { key: "krakenfiles", label: "KrakenFiles", configured: false },
  { key: "uploadrar", label: "Uploadrar", configured: false },
  { key: "up4ever", label: "Up-4ever", configured: false },
]

export default function PublishPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.jobId as string

  const [clips, setClips] = useState<ClipData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedClipId, setSelectedClipId] = useState<string>("")
  const [selectedPlatform, setSelectedPlatform] = useState<PublishTarget>("instagram")
  const [publishTitle, setPublishTitle] = useState("")
  const [publishDescription, setPublishDescription] = useState("")
  const [publishStatuses, setPublishStatuses] = useState<PublishStatus[]>([])
  const [connectedAccounts, setConnectedAccounts] = useState<ConnectedAccount>({
    youtube: false,
    instagram: false,
  })
  const [hosts, setHosts] = useState<HostInfo[]>(DEFAULT_HOSTS)
  const [selectedHosts, setSelectedHosts] = useState<HostKey[]>([])
  const [distributing, setDistributing] = useState(false)
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
        setSelectedClipId((prev) => prev || clipsData[0].id || clipsData[0]._id || "")
      }
    } catch {
      setError("Could not load clips.")
    } finally {
      setLoading(false)
    }
  }, [projectId])

  const loadAuthStatus = useCallback(async () => {
    try {
      const response = await api.get("/api/v1/auth/status")
      setConnectedAccounts({
        youtube: Boolean(response.data?.youtube),
        instagram: Boolean(response.data?.instagram),
      })
      const hostMap = response.data?.hosts || {}
      setHosts((prev) =>
        prev.map((host) => ({
          ...host,
          configured: Boolean(hostMap[host.key]),
        }))
      )
      setSelectedHosts((prev) => {
        if (prev.length > 0) return prev
        return DEFAULT_HOSTS.map((h) => h.key).filter((key) => Boolean(hostMap[key]))
      })
    } catch {
      // Keep prior UI state if auth status is unavailable.
    }
  }, [])

  useEffect(() => {
    const token = localStorage.getItem("token")
    if (!token) {
      router.push("/login")
      return
    }
    loadClips()
    loadAuthStatus()
  }, [loadClips, loadAuthStatus, router])

  useEffect(() => {
    const onFocus = () => {
      loadAuthStatus()
    }
    window.addEventListener("focus", onFocus)
    return () => window.removeEventListener("focus", onFocus)
  }, [loadAuthStatus])

  const selectedClip = useMemo(
    () => clips.find((c) => (c.id || c._id) === selectedClipId),
    [clips, selectedClipId]
  )

  const handleConnectAccount = async (platform: PublishTarget) => {
    setConnectingPlatform(platform)
    try {
      const response = await api.post(`/api/v1/auth/${platform}`)
      if (response.data?.auth_url) {
        window.open(response.data.auth_url, "_blank", "width=600,height=700")
        showToast(`Complete ${platform} login in the new window, then return here.`, "info")
      } else {
        showToast("Could not start OAuth. Check backend credentials.", "error")
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail || `Failed to start ${platform} OAuth.`, "error")
    } finally {
      setConnectingPlatform(null)
    }
  }

  const getPublishStatus = (clipId: string, target: PublishTarget | HostKey) =>
    publishStatuses.find((s) => s.clipId === clipId && s.target === target)

  const upsertStatus = (entry: PublishStatus) => {
    setPublishStatuses((prev) => [
      ...prev.filter((s) => !(s.clipId === entry.clipId && s.target === entry.target)),
      entry,
    ])
  }

  const pollPublishStatus = async (clipId: string, platform: PublishTarget) => {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      await sleep(2000)
      const response = await api.get(`/api/v1/clips/${clipId}/publish/status`)
      const publishStatus = response.data?.publish_status as string | undefined
      const publishedUrl = response.data?.published_url as string | undefined
      if (publishStatus === "published") {
        return { ok: true as const, url: publishedUrl }
      }
      if (publishStatus === "error") {
        const detail =
          typeof response.data?.result === "object" && response.data?.result?.error
            ? String(response.data.result.error)
            : "Publish failed"
        return { ok: false as const, error: detail }
      }
    }
    return { ok: false as const, error: "Publish timed out. Check status later." }
  }

  const handlePublish = async () => {
    if (!selectedClipId || !publishTitle.trim()) return

    const platform = PLATFORMS.find((p) => p.key === selectedPlatform)!
    if (!connectedAccounts[selectedPlatform]) {
      showToast(`Connect your ${platform.shortLabel} account first.`, "error")
      return
    }

    if (!selectedClip?.cloudinary_clip_url) {
      showToast("This clip has no Cloudinary URL. Re-process the clip before publishing.", "error")
      return
    }

    upsertStatus({
      clipId: selectedClipId,
      target: selectedPlatform,
      status: "publishing",
    })

    try {
      await api.post(`/api/v1/clips/${selectedClipId}/publish/${selectedPlatform}`, {
        title: publishTitle.trim(),
        description: publishDescription.trim(),
      })

      const result = await pollPublishStatus(selectedClipId, selectedPlatform)
      const now = new Date().toISOString()
      if (result.ok) {
        upsertStatus({
          clipId: selectedClipId,
          target: selectedPlatform,
          status: "success",
          message: result.url
            ? `Published to ${platform.label}: ${result.url}`
            : `Published to ${platform.label} successfully!`,
          url: result.url,
          timestamp: now,
        })
        showToast(`Published to ${platform.label}!`, "success")
        await loadClips()
      } else {
        upsertStatus({
          clipId: selectedClipId,
          target: selectedPlatform,
          status: "error",
          message: result.error,
          timestamp: now,
        })
        showToast(result.error, "error")
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      const now = new Date().toISOString()
      upsertStatus({
        clipId: selectedClipId,
        target: selectedPlatform,
        status: "error",
        message: detail || "Publish failed. Please try again.",
        timestamp: now,
      })
      showToast(detail || "Publish failed. Please try again.", "error")
    }
  }

  const pollDistributeStatus = async (clipId: string, hostsToWatch: HostKey[]) => {
    for (let attempt = 0; attempt < 90; attempt += 1) {
      await sleep(2000)
      const response = await api.get(`/api/v1/clips/${clipId}/distribute/status`)
      const hostUploads = (response.data?.host_uploads || {}) as Record<string, HostUploadState>
      const settled = hostsToWatch.every((host) => {
        const status = hostUploads[host]?.status
        return status === "ready" || status === "error" || status === "skipped"
      })
      if (settled) {
        return hostUploads
      }
    }
    const response = await api.get(`/api/v1/clips/${clipId}/distribute/status`)
    return (response.data?.host_uploads || {}) as Record<string, HostUploadState>
  }

  const handleDistribute = async () => {
    if (!selectedClipId || selectedHosts.length === 0) return

    const configuredSelected = selectedHosts.filter((key) => hosts.find((h) => h.key === key)?.configured)
    if (configuredSelected.length === 0) {
      showToast("No configured hosts selected. Add API keys in backend env.", "error")
      return
    }

    setDistributing(true)
    for (const host of configuredSelected) {
      upsertStatus({
        clipId: selectedClipId,
        target: host,
        status: "publishing",
      })
    }

    try {
      await api.post(`/api/v1/clips/${selectedClipId}/distribute`, {
        hosts: configuredSelected,
      })
      const hostUploads = await pollDistributeStatus(selectedClipId, configuredSelected)
      const now = new Date().toISOString()

      for (const host of configuredSelected) {
        const state = hostUploads[host]
        const label = hosts.find((h) => h.key === host)?.label || host
        if (state?.status === "ready" && state.url) {
          upsertStatus({
            clipId: selectedClipId,
            target: host,
            status: "success",
            message: `${label}: ${state.url}`,
            url: state.url,
            timestamp: now,
          })
        } else if (state?.status === "skipped") {
          upsertStatus({
            clipId: selectedClipId,
            target: host,
            status: "error",
            message: `${label}: skipped (${state.error || "not configured"})`,
            timestamp: now,
          })
        } else {
          upsertStatus({
            clipId: selectedClipId,
            target: host,
            status: "error",
            message: `${label}: ${state?.error || "Upload failed"}`,
            timestamp: now,
          })
        }
      }

      setClips((prev) =>
        prev.map((clip) => {
          const id = clip.id || clip._id
          if (id !== selectedClipId) return clip
          return { ...clip, host_uploads: hostUploads }
        })
      )
      showToast("Host uploads finished.", "success")
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail || "Host distribute failed.", "error")
    } finally {
      setDistributing(false)
    }
  }

  const toggleHost = (key: HostKey) => {
    setSelectedHosts((prev) => (prev.includes(key) ? prev.filter((h) => h !== key) : [...prev, key]))
  }

  const currentStatus = getPublishStatus(selectedClipId, selectedPlatform)
  const isPublishing = currentStatus?.status === "publishing"
  const publishHistory = publishStatuses.filter((s) => s.status === "success" || s.status === "error")

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f7f8fc] text-sm text-[#737686]">
        Loading publish tools…
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#f7f8fc] text-[#191b23]">
      <header className="border-b border-[#e1e2ed] bg-white px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center gap-3">
          <button
            onClick={() => router.push(`/project/${projectId}/clips`)}
            className="rounded-lg border border-[#e1e2ed] px-3 py-1.5 text-xs text-[#737686] hover:border-[#004ac6] hover:text-[#004ac6]"
          >
            ← Clips
          </button>
          <button
            onClick={() => setActiveTab("publish")}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
              activeTab === "publish" ? "bg-white shadow-sm text-[#191b23]" : "text-[#737686] hover:text-[#191b23]"
            }`}
          >
            Publish
          </button>
          <button
            onClick={() => setActiveTab("history")}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium ${
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
        {activeTab === "publish" && (
          <>
            <div className="mb-6">
              <h1 className="text-2xl font-bold">Publish Clips</h1>
              <p className="mt-1 text-sm text-[#434655]">
                Publish to Instagram Reels / YouTube Shorts, and upload the same clip to PPD file hosts in parallel.
              </p>
            </div>

            {error && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <section className="mb-6 rounded-xl border border-[#e1e2ed] bg-white p-5 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold">Connected Accounts</h2>
                <button
                  onClick={() => loadAuthStatus()}
                  className="text-[11px] font-medium text-[#004ac6] hover:underline"
                >
                  Refresh status
                </button>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {PLATFORMS.map((platform) => {
                  const isConnected = connectedAccounts[platform.key]
                  const isConnecting = connectingPlatform === platform.key
                  return (
                    <div
                      key={platform.key}
                      className={`flex items-center justify-between rounded-xl border p-4 ${
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
                        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
                          Connected
                        </span>
                      ) : (
                        <button
                          onClick={() => handleConnectAccount(platform.key)}
                          disabled={isConnecting}
                          className={`rounded-lg px-3 py-1.5 text-xs font-medium text-white disabled:opacity-60 ${platform.connectBg}`}
                        >
                          {isConnecting ? "Connecting…" : "Connect"}
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
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
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-medium">
                                {clip.label ||
                                  `Clip ${formatDuration(clip.start_time)} – ${formatDuration(clip.end_time)}`}
                              </p>
                              <div className="mt-1.5 flex flex-wrap gap-1.5">
                                {!clip.cloudinary_clip_url && (
                                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                                    No Cloudinary URL
                                  </span>
                                )}
                                {ytStatus?.status === "success" && (
                                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
                                    YouTube
                                  </span>
                                )}
                                {igStatus?.status === "success" && (
                                  <span className="rounded-full bg-pink-100 px-2 py-0.5 text-[10px] font-semibold text-pink-700">
                                    Instagram
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

                <div className="space-y-6">
                  <section className="rounded-xl border border-[#e1e2ed] bg-white p-6 shadow-sm">
                    <h2 className="mb-4 text-base font-semibold">Social Publish</h2>

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

                    {!connectedAccounts[selectedPlatform] && (
                      <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-700">
                        Connect your {PLATFORMS.find((p) => p.key === selectedPlatform)?.shortLabel} account
                        above to publish.
                      </div>
                    )}

                    {selectedClip && !selectedClip.cloudinary_clip_url && (
                      <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-700">
                        This clip has no Cloudinary URL. Instagram/YouTube publish requires Cloudinary.
                      </div>
                    )}

                    <div className="mb-4">
                      <label className="mb-1.5 block text-xs font-medium uppercase text-[#737686]">
                        Title <span className="text-red-500">*</span>
                      </label>
                      <input
                        value={publishTitle}
                        onChange={(e) => setPublishTitle(e.target.value)}
                        placeholder="Enter a catchy title..."
                        maxLength={100}
                        className="w-full rounded-lg border border-[#d4d7e8] px-3 py-2 text-sm outline-none focus:border-[#004ac6]"
                      />
                    </div>

                    <div className="mb-6">
                      <label className="mb-1.5 block text-xs font-medium uppercase text-[#737686]">
                        Description / caption
                      </label>
                      <textarea
                        value={publishDescription}
                        onChange={(e) => setPublishDescription(e.target.value)}
                        rows={3}
                        maxLength={500}
                        placeholder="Add a description, hashtags..."
                        className="w-full rounded-lg border border-[#d4d7e8] px-3 py-2 text-sm outline-none focus:border-[#004ac6]"
                      />
                    </div>

                    <button
                      type="button"
                      onClick={handlePublish}
                      disabled={
                        isPublishing ||
                        !selectedClipId ||
                        !publishTitle.trim() ||
                        !connectedAccounts[selectedPlatform] ||
                        !selectedClip?.cloudinary_clip_url
                      }
                      className="w-full rounded-lg bg-gradient-to-r from-[#004ac6] to-[#712ae2] py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isPublishing
                        ? "Publishing…"
                        : `Publish to ${PLATFORMS.find((p) => p.key === selectedPlatform)?.label}`}
                    </button>

                    {currentStatus?.status === "success" && (
                      <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                        {currentStatus.message}
                        {currentStatus.url && (
                          <a
                            href={currentStatus.url}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-1 block underline"
                          >
                            Open post
                          </a>
                        )}
                      </div>
                    )}
                    {currentStatus?.status === "error" && (
                      <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                        {currentStatus.message}
                      </div>
                    )}
                  </section>

                  <section className="rounded-xl border border-[#e1e2ed] bg-white p-6 shadow-sm">
                    <h2 className="mb-1 text-base font-semibold">File Hosts</h2>
                    <p className="mb-4 text-xs text-[#737686]">
                      Upload the selected clip to KrakenFiles, Uploadrar, and Up-4ever in parallel.
                    </p>

                    <div className="mb-4 space-y-2">
                      {hosts.map((host) => {
                        const checked = selectedHosts.includes(host.key)
                        const existing = selectedClip?.host_uploads?.[host.key]
                        return (
                          <label
                            key={host.key}
                            className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 ${
                              host.configured ? "border-[#e1e2ed] bg-white" : "border-[#ececf5] bg-[#f7f8fc] opacity-70"
                            }`}
                          >
                            <input
                              type="checkbox"
                              className="mt-1"
                              checked={checked}
                              disabled={!host.configured || distributing}
                              onChange={() => toggleHost(host.key)}
                            />
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-medium">{host.label}</span>
                                <span
                                  className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                                    host.configured
                                      ? "bg-emerald-100 text-emerald-700"
                                      : "bg-[#ededf9] text-[#737686]"
                                  }`}
                                >
                                  {host.configured ? "Configured" : "Missing API key"}
                                </span>
                              </div>
                              {existing?.url && (
                                <a
                                  href={existing.url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="mt-1 block truncate text-[11px] text-[#004ac6] underline"
                                >
                                  {existing.url}
                                </a>
                              )}
                              {existing?.status === "error" && existing.error && (
                                <p className="mt-1 text-[11px] text-red-600">{existing.error}</p>
                              )}
                            </div>
                          </label>
                        )
                      })}
                    </div>

                    <button
                      type="button"
                      onClick={handleDistribute}
                      disabled={distributing || !selectedClipId || selectedHosts.length === 0}
                      className="w-full rounded-lg border border-[#004ac6] bg-white py-2.5 text-sm font-medium text-[#004ac6] hover:bg-[#f0f5ff] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {distributing ? "Uploading to hosts…" : "Upload to selected hosts"}
                    </button>
                  </section>
                </div>
              </div>
            )}
          </>
        )}

        {activeTab === "history" && (
          <>
            <div className="mb-6">
              <h1 className="text-2xl font-bold">Publish History</h1>
              <p className="mt-1 text-sm text-[#434655]">
                Social publishes and file-host uploads for this session.
              </p>
            </div>

            {publishHistory.length === 0 ? (
              <div className="rounded-xl border border-dashed border-[#c3c6d7] bg-white p-12 text-center">
                <p className="text-sm font-medium text-[#737686]">No publish history yet.</p>
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
                  const platform = PLATFORMS.find((p) => p.key === record.target)
                  const host = hosts.find((h) => h.key === record.target)
                  const label = platform?.label || host?.label || String(record.target)
                  return (
                    <div
                      key={`${record.clipId}-${record.target}-${i}`}
                      className={`flex items-center gap-4 rounded-xl border bg-white p-4 shadow-sm ${
                        record.status === "success" ? "border-emerald-100" : "border-red-100"
                      }`}
                    >
                      <div className="h-12 w-20 flex-shrink-0 overflow-hidden rounded-lg bg-[#ededf9]">
                        {clip?.thumbnail_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={clip.thumbnail_url} alt="clip" className="h-full w-full object-cover" />
                        ) : (
                          <div className="flex h-full items-center justify-center text-[9px] text-[#737686]">
                            No preview
                          </div>
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">
                          {clip?.label ||
                            `Clip ${formatDuration(clip?.start_time)} – ${formatDuration(clip?.end_time)}`}
                        </p>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-[#737686]">
                          <span>{label}</span>
                          <span>·</span>
                          <span>{formatTimestamp(record.timestamp)}</span>
                        </div>
                        {record.url && (
                          <a
                            href={record.url}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-1 block truncate text-[11px] text-[#004ac6] underline"
                          >
                            {record.url}
                          </a>
                        )}
                        {!record.url && record.message && (
                          <p className="mt-1 truncate text-[11px] text-[#737686]">{record.message}</p>
                        )}
                      </div>
                      <div className="flex-shrink-0">
                        {record.status === "success" ? (
                          <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
                            Success
                          </span>
                        ) : (
                          <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-700">
                            Failed
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

      {toast && (
        <div
          className={`fixed bottom-6 left-1/2 z-[200] -translate-x-1/2 rounded-xl px-5 py-3 text-sm font-medium text-white shadow-lg ${
            toast.type === "success" ? "bg-emerald-600" : toast.type === "error" ? "bg-red-600" : "bg-[#191b23]"
          }`}
        >
          {toast.message}
        </div>
      )}
    </div>
  )
}
