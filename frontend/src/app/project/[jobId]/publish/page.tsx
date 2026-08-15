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
  file_size_bytes?: number | null
  interest_score?: number | null
  interest_audio?: number | null
  interest_motion?: number | null
  is_recommended?: boolean
  host_uploads?: Record<string, HostUploadState>
  publish_status?: string | null
  publish_platform?: string | null
  published_url?: string | null
}

type PublishTarget = "youtube" | "instagram"
type HostKey = "krakenfiles" | "uploadrar" | "up4ever"

type BracketInfo = {
  name: string
  label: string
}

type HostRecommendation = {
  key: HostKey
  label: string
  configured: boolean
  role: "primary" | "backup" | null
}

type DistributeRecommendations = {
  size_bytes: number
  bracket: BracketInfo
  primary: HostKey
  backup: HostKey | null
  recommended_hosts: HostKey[]
  all_hosts: HostRecommendation[]
}

type HostUploadState = {
  status?: string
  url?: string | null
  file_code?: string | null
  error?: string | null
  updated_at?: string | null
}

type QualityAssetRow = {
  quality: string
  status?: string | null
  local_path?: string | null
  file_size_bytes?: number | null
  host?: string | null
  host_configured?: boolean
  host_status?: string | null
  host_url?: string | null
  host_error?: string | null
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
  role?: "primary" | "backup" | null
}

const BYTES_MB = 1024 * 1024
const BYTES_GB = 1024 * 1024 * 1024

function formatBytes(bytes?: number | null) {
  if (!bytes || bytes < 1) return "—"
  if (bytes < BYTES_MB) return `${Math.round(bytes / 1024)} KB`
  if (bytes < BYTES_GB) return `${(bytes / BYTES_MB).toFixed(1)} MB`
  return `${(bytes / BYTES_GB).toFixed(2)} GB`
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
  const [projectTitle, setProjectTitle] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedClipId, setSelectedClipId] = useState<string>("")
  const [checkedClipIds, setCheckedClipIds] = useState<string[]>([])
  const [clipListMode, setClipListMode] = useState<"recommended" | "chronological">("recommended")
  const [selectedPlatform, setSelectedPlatform] = useState<PublishTarget>("instagram")
  const [publishingSelected, setPublishingSelected] = useState(false)
  const [publishTitle, setPublishTitle] = useState("")
  const [publishDescription, setPublishDescription] = useState("")
  const [copyPoolCaptionId, setCopyPoolCaptionId] = useState<string | null>(null)
  const [excludedCopyPoolIds, setExcludedCopyPoolIds] = useState<string[]>([])
  const [loadingCaption, setLoadingCaption] = useState(false)
  const [publishStatuses, setPublishStatuses] = useState<PublishStatus[]>([])
  const [connectedAccounts, setConnectedAccounts] = useState<ConnectedAccount>({
    youtube: false,
    instagram: false,
  })
  const [hosts, setHosts] = useState<HostInfo[]>(DEFAULT_HOSTS)
  const [selectedHosts, setSelectedHosts] = useState<HostKey[]>([])
  const [recommendations, setRecommendations] = useState<DistributeRecommendations | null>(null)
  const [loadingRecommendations, setLoadingRecommendations] = useState(false)
  const [distributing, setDistributing] = useState(false)
  const [publishingAll, setPublishingAll] = useState(false)
  const [retryingFailed, setRetryingFailed] = useState(false)
  const [qualityRows, setQualityRows] = useState<QualityAssetRow[]>([])
  const [clipsExpireAt, setClipsExpireAt] = useState<string | null>(null)
  const [retryingQualities, setRetryingQualities] = useState(false)
  const [showClipDistribute, setShowClipDistribute] = useState(false)
  const [publishProgress, setPublishProgress] = useState<{
    queued: number
    processing: number
    published: number
    error: number
    publishable: number
    in_flight: number
    active: boolean
  } | null>(null)
  const [connectingPlatform, setConnectingPlatform] = useState<PublishTarget | null>(null)
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" | "info" } | null>(null)
  const [activeTab, setActiveTab] = useState<"publish" | "history">("publish")

  const showToast = (message: string, type: "success" | "error" | "info" = "info") => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3500)
  }

  const loadQualities = useCallback(async () => {
    try {
      const response = await api.get(`/api/v1/projects/${projectId}/qualities`)
      setQualityRows(Array.isArray(response.data?.qualities) ? response.data.qualities : [])
      setClipsExpireAt(response.data?.clips_expire_at || null)
    } catch {
      // Fall back to project payload quality_assets if dedicated endpoint fails.
    }
  }, [projectId])

  const loadClips = useCallback(async () => {
    try {
      const [clipsRes, projectRes] = await Promise.all([
        api.get(`/api/v1/projects/${projectId}/clips`),
        api.get(`/api/v1/projects/${projectId}`),
      ])
      const clipsData = Array.isArray(clipsRes.data) ? clipsRes.data : []
      setClips(clipsData)
      if (clipsData.length > 0) {
        setSelectedClipId((prev) => prev || clipsData[0].id || clipsData[0]._id || "")
        setCheckedClipIds((prev) => {
          if (prev.length > 0) return prev
          const recommended = clipsData
            .filter((c: ClipData) => c.is_recommended)
            .map((c: ClipData) => c.id || c._id || "")
            .filter(Boolean)
          return recommended
        })
      }
      const title = String(projectRes.data?.title || "")
      setProjectTitle(title)
      setPublishTitle((prev) => prev || title)
      setClipsExpireAt(projectRes.data?.clips_expire_at || null)

      const assets = projectRes.data?.quality_assets || {}
      if (assets && typeof assets === "object") {
        const rows: QualityAssetRow[] = ["240", "480", "720", "1080"].map((quality) => {
          const asset = assets[quality] || {}
          return {
            quality,
            status: asset.status,
            local_path: asset.local_path,
            file_size_bytes: asset.file_size_bytes,
            host: asset.host,
            host_status: asset.host_status,
            host_url: asset.host_url,
            host_error: asset.host_error,
          }
        })
        setQualityRows(rows)
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
    } catch {
      // Keep prior UI state if auth status is unavailable.
    }
  }, [])

  const loadRecommendations = useCallback(async (clipId: string) => {
    if (!clipId) {
      setRecommendations(null)
      return
    }
    setLoadingRecommendations(true)
    try {
      const response = await api.get(`/api/v1/clips/${clipId}/distribute/recommendations`)
      const data = response.data as DistributeRecommendations
      setRecommendations(data)
      const recommended = data.recommended_hosts.filter((key) =>
        data.all_hosts.find((host) => host.key === key)?.configured
      )
      setSelectedHosts(recommended)
    } catch {
      setRecommendations(null)
    } finally {
      setLoadingRecommendations(false)
    }
  }, [])

  const loadPublishProgress = useCallback(async () => {
    try {
      const response = await api.get(`/api/v1/projects/${projectId}/publish/instagram/status`)
      const counts = response.data?.counts || {}
      setPublishProgress({
        queued: Number(counts.queued || 0),
        processing: Number(counts.processing || 0),
        published: Number(counts.published || 0),
        error: Number(counts.error || 0),
        publishable: Number(counts.publishable || 0),
        in_flight: Number(counts.in_flight || 0),
        active: Boolean(response.data?.active),
      })
    } catch {
      // Keep previous progress if status endpoint is unavailable.
    }
  }, [projectId])

  const fetchCopyPoolCaption = useCallback(
    async (opts?: { skipCurrent?: boolean }) => {
      setLoadingCaption(true)
      try {
        let exclude = excludedCopyPoolIds
        if (opts?.skipCurrent && copyPoolCaptionId) {
          exclude = [...excludedCopyPoolIds, copyPoolCaptionId].slice(-50)
          setExcludedCopyPoolIds(exclude)
        }
        const params =
          exclude.length > 0 ? { exclude: exclude.join(",") } : undefined
        const response = await api.get("/api/v1/copy-pool/descriptions/random", { params })
        const data = response.data?.data || {}
        const text = String(data.description || "").trim()
        if (!text) {
          showToast("Copy pool returned an empty caption.", "error")
          return
        }
        setPublishDescription(text)
        setCopyPoolCaptionId(data.id ? String(data.id) : null)
      } catch (err: unknown) {
        const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
        let message = "Could not fetch caption from copy pool."
        if (typeof detail === "string") {
          message = detail
        } else if (detail && typeof detail === "object" && "message" in detail) {
          message = String((detail as { message?: string }).message || message)
        }
        showToast(message, "error")
      } finally {
        setLoadingCaption(false)
      }
    },
    [copyPoolCaptionId, excludedCopyPoolIds]
  )

  useEffect(() => {
    const token = localStorage.getItem("token")
    if (!token) {
      router.push("/login")
      return
    }
    loadClips()
    loadAuthStatus()
    loadPublishProgress()
    loadQualities()
    void fetchCopyPoolCaption()
  }, [loadClips, loadAuthStatus, loadPublishProgress, loadQualities, router]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const busy =
      publishingAll || publishingSelected || retryingFailed || Boolean(publishProgress?.active)
    if (!busy) return
    const interval = setInterval(() => {
      loadClips()
      loadPublishProgress()
    }, 4000)
    return () => clearInterval(interval)
  }, [
    publishingAll,
    publishingSelected,
    retryingFailed,
    publishProgress?.active,
    loadClips,
    loadPublishProgress,
  ])

  useEffect(() => {
    const hostBusy = qualityRows.some((row) => (row.host_status || "").toLowerCase() === "uploading")
    if (!hostBusy) return
    const interval = setInterval(() => {
      void loadQualities()
    }, 4000)
    return () => clearInterval(interval)
  }, [qualityRows, loadQualities])

  useEffect(() => {
    const onFocus = () => {
      loadAuthStatus()
    }
    const onMessage = (event: MessageEvent) => {
      const data = event.data
      if (!data || data.type !== "oauth-complete") return
      loadAuthStatus()
      if (data.status === "connected") {
        showToast(`${String(data.platform || "Account")} connected.`, "success")
      } else {
        showToast(String(data.message || "Could not connect account."), "error")
      }
    }
    window.addEventListener("focus", onFocus)
    window.addEventListener("message", onMessage)
    return () => {
      window.removeEventListener("focus", onFocus)
      window.removeEventListener("message", onMessage)
    }
  }, [loadAuthStatus])

  useEffect(() => {
    if (!selectedClipId) {
      setRecommendations(null)
      return
    }
    loadRecommendations(selectedClipId)
  }, [selectedClipId, loadRecommendations])

  const selectedClip = useMemo(
    () => clips.find((c) => (c.id || c._id) === selectedClipId),
    [clips, selectedClipId]
  )

  const clipIdOf = (clip: ClipData) => clip.id || clip._id || ""

  const recommendedClips = useMemo(
    () => clips.filter((c) => c.is_recommended && c.cloudinary_clip_url),
    [clips]
  )

  const displayedClips = useMemo(() => {
    const sorted = [...clips]
    if (clipListMode === "recommended") {
      sorted.sort((a, b) => {
        const rec = Number(Boolean(b.is_recommended)) - Number(Boolean(a.is_recommended))
        if (rec !== 0) return rec
        const scoreDiff = (b.interest_score ?? -1) - (a.interest_score ?? -1)
        if (scoreDiff !== 0) return scoreDiff
        return (a.start_time ?? 0) - (b.start_time ?? 0)
      })
    } else {
      sorted.sort((a, b) => (a.start_time ?? 0) - (b.start_time ?? 0))
    }
    return sorted
  }, [clips, clipListMode])

  const displayHosts = useMemo<HostInfo[]>(() => {
    if (recommendations?.all_hosts) {
      return recommendations.all_hosts.map((host) => ({
        key: host.key,
        label: host.label,
        configured: host.configured,
        role: host.role,
      }))
    }
    return hosts
  }, [recommendations, hosts])

  const recommendedHosts = useMemo(() => {
    if (!recommendations) return [] as HostKey[]
    return recommendations.recommended_hosts.filter((key) =>
      recommendations.all_hosts.find((host) => host.key === key)?.configured
    )
  }, [recommendations])

  const selectionMatchesRecommended = useMemo(() => {
    if (recommendedHosts.length === 0) return false
    if (selectedHosts.length !== recommendedHosts.length) return false
    return recommendedHosts.every((host) => selectedHosts.includes(host))
  }, [selectedHosts, recommendedHosts])

  const selectedClipSizeBytes = recommendations?.size_bytes ?? selectedClip?.file_size_bytes ?? null

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
    const caption = publishDescription.trim()
    const title =
      publishTitle.trim() ||
      selectedClip?.label ||
      projectTitle ||
      (selectedPlatform === "instagram" ? "Reel" : "")
    if (!selectedClipId) return
    if (selectedPlatform === "youtube" && !title.trim()) return

    const platform = PLATFORMS.find((p) => p.key === selectedPlatform)!
    if (!connectedAccounts[selectedPlatform]) {
      showToast(`Connect your ${platform.shortLabel} account first.`, "error")
      return
    }

    if (!selectedClip?.cloudinary_clip_url) {
      showToast("This clip has no Cloudinary URL. Re-process the clip before publishing.", "error")
      return
    }

    if (selectedPlatform === "instagram" && !caption) {
      showToast("Fetch a caption from the copy pool (or write your own).", "error")
      return
    }

    upsertStatus({
      clipId: selectedClipId,
      target: selectedPlatform,
      status: "publishing",
    })

    try {
      await api.post(`/api/v1/clips/${selectedClipId}/publish/${selectedPlatform}`, {
        title,
        description: caption,
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

    const configuredSelected = selectedHosts.filter((key) =>
      displayHosts.find((host) => host.key === key)?.configured
    )
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
      const distributeBody = selectionMatchesRecommended
        ? { mode: "auto" as const }
        : { mode: "manual" as const, hosts: configuredSelected }
      await api.post(`/api/v1/clips/${selectedClipId}/distribute`, distributeBody)
      const hostUploads = await pollDistributeStatus(selectedClipId, configuredSelected)
      const now = new Date().toISOString()

      for (const host of configuredSelected) {
        const state = hostUploads[host]
        const label = displayHosts.find((h) => h.key === host)?.label || host
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

  const applyRecommendedHosts = () => {
    if (!recommendations) return
    const recommended = recommendations.recommended_hosts.filter((key) =>
      recommendations.all_hosts.find((host) => host.key === key)?.configured
    )
    setSelectedHosts(recommended)
  }

  const handlePublishAllInstagram = async () => {
    if (!connectedAccounts.instagram) {
      showToast("Connect your Instagram account first.", "error")
      return
    }
    const caption = publishDescription.trim()
    if (!caption) {
      showToast("Fetch a caption from the copy pool (or write your own), then publish.", "error")
      return
    }
    if (recommendedClips.length === 0) {
      showToast(
        "No recommended clips yet. Regenerate clips to score interest, or select clips and publish selected.",
        "error"
      )
      return
    }

    setPublishingAll(true)
    try {
      const response = await api.post(`/api/v1/projects/${projectId}/publish/instagram`, {
        title: publishTitle.trim() || projectTitle,
        description: caption,
        recommended_only: true,
      })
      showToast(
        response.data?.message ||
          `Queued ${response.data?.clip_count || recommendedClips.length} recommended clips for Instagram.`,
        "success"
      )
      await Promise.all([loadClips(), loadPublishProgress()])
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail || "Could not queue Instagram publish.", "error")
    } finally {
      setPublishingAll(false)
    }
  }

  const handlePublishSelectedInstagram = async () => {
    if (!connectedAccounts.instagram) {
      showToast("Connect your Instagram account first.", "error")
      return
    }
    const caption = publishDescription.trim()
    if (!caption) {
      showToast("Fetch a caption from the copy pool (or write your own), then publish.", "error")
      return
    }
    const selectedReady = checkedClipIds.filter((id) => {
      const clip = clips.find((c) => clipIdOf(c) === id)
      return clip && (clip.status || "").toLowerCase() === "ready" && clip.cloudinary_clip_url
    })
    if (selectedReady.length === 0) {
      showToast("Select at least one ready clip with a Cloudinary URL.", "error")
      return
    }

    setPublishingSelected(true)
    try {
      const response = await api.post(`/api/v1/projects/${projectId}/publish/instagram`, {
        title: publishTitle.trim() || projectTitle,
        description: caption,
        clip_ids: selectedReady,
        recommended_only: false,
      })
      showToast(
        response.data?.message || `Queued ${response.data?.clip_count || selectedReady.length} selected clips.`,
        "success"
      )
      await Promise.all([loadClips(), loadPublishProgress()])
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail || "Could not queue selected Instagram publishes.", "error")
    } finally {
      setPublishingSelected(false)
    }
  }

  const toggleCheckedClip = (clipId: string) => {
    setCheckedClipIds((prev) =>
      prev.includes(clipId) ? prev.filter((id) => id !== clipId) : [...prev, clipId]
    )
  }

  const selectRecommendedClips = () => {
    setCheckedClipIds(
      clips
        .filter((c) => c.is_recommended)
        .map(clipIdOf)
        .filter(Boolean)
    )
  }

  const selectAllClips = () => {
    setCheckedClipIds(clips.map(clipIdOf).filter(Boolean))
  }

  const clearCheckedClips = () => {
    setCheckedClipIds([])
  }

  const handleRetryQualityHosts = async () => {
    setRetryingQualities(true)
    try {
      const response = await api.post(`/api/v1/projects/${projectId}/distribute/qualities`, {
        only_failed: true,
      })
      showToast(response.data?.message || "Retrying full-movie host uploads…", "info")
      await loadQualities()
      await loadClips()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail || "Could not retry quality host uploads.", "error")
    } finally {
      setRetryingQualities(false)
    }
  }

  const handleRetryFailedInstagram = async () => {
    if (!connectedAccounts.instagram) {
      showToast("Connect your Instagram account first.", "error")
      return
    }
    const caption = publishDescription.trim()
    if (!caption) {
      showToast("Fetch a caption from the copy pool (or write your own).", "error")
      return
    }
    setRetryingFailed(true)
    try {
      const response = await api.post(`/api/v1/projects/${projectId}/publish/instagram/retry`, {
        title: publishTitle.trim() || projectTitle,
        description: caption,
      })
      showToast(response.data?.message || "Retrying failed publishes…", "success")
      await Promise.all([loadClips(), loadPublishProgress()])
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail || "Could not retry failed publishes.", "error")
    } finally {
      setRetryingFailed(false)
    }
  }

  const currentStatus = getPublishStatus(selectedClipId, selectedPlatform)
  const isPublishing = currentStatus?.status === "publishing"
  const publishHistory = publishStatuses.filter((s) => s.status === "success" || s.status === "error")
  const effectiveCaption = publishDescription.trim()
  const failedPublishCount =
    publishProgress?.error ??
    clips.filter((c) => (c.publish_status || "").toLowerCase() === "error").length
  const progressTotal = Math.max(publishProgress?.publishable || 0, 1)
  const progressDone = (publishProgress?.published || 0) + (publishProgress?.error || 0)
  const progressPct = Math.min(100, Math.round((progressDone / progressTotal) * 100))

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
                Full movies are sorted by quality at upload (240/480/720/1080) and sent to hosts
                automatically. Popular clips are cut from 720p and published to Instagram or YouTube.
              </p>
            </div>

            <section className="mb-6 rounded-xl border border-[#e1e2ed] bg-white p-5 shadow-sm">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold">Full movie qualities (hosts)</h2>
                <button
                  type="button"
                  onClick={handleRetryQualityHosts}
                  disabled={retryingQualities}
                  className="rounded-lg border border-[#e1e2ed] px-3 py-1.5 text-xs font-semibold text-[#434655] hover:border-[#004ac6] hover:text-[#004ac6] disabled:opacity-50"
                >
                  {retryingQualities ? "Retrying…" : "Retry failed host uploads"}
                </button>
              </div>
              {clipsExpireAt && (
                <p className="mb-3 text-[11px] text-[#737686]">
                  Clips auto-delete after {formatTimestamp(clipsExpireAt)} (full-movie host links stay).
                </p>
              )}
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {(qualityRows.length
                  ? qualityRows
                  : (["240", "480", "720", "1080"] as const).map(
                      (quality): QualityAssetRow => ({
                        quality,
                        status: "pending",
                      }),
                    )
                ).map((row) => (
                  <div
                    key={row.quality}
                    className="rounded-lg border border-[#e1e2ed] bg-[#f7f8fc] px-3 py-2.5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold">{row.quality}p</p>
                      <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold uppercase text-[#737686]">
                        {row.status || "—"}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-[#737686]">
                      Host: {row.host || "—"} · {row.host_status || "pending"}
                      {row.file_size_bytes ? ` · ${formatBytes(row.file_size_bytes)}` : ""}
                    </p>
                    {row.quality === "720" && (
                      <p className="mt-1 text-[10px] font-semibold text-[#004ac6]">Clip source</p>
                    )}
                    {row.host_url ? (
                      <a
                        href={row.host_url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-1 block truncate text-[11px] text-[#004ac6] underline"
                      >
                        {row.host_url}
                      </a>
                    ) : row.host_error ? (
                      <p className="mt-1 text-[11px] text-amber-700">{row.host_error}</p>
                    ) : null}
                  </div>
                ))}
              </div>
            </section>

            <section className="mb-6 rounded-xl border border-[#e1e2ed] bg-white p-5 shadow-sm">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold">Instagram caption (copy pool)</h2>
                  <p className="text-[11px] text-[#737686]">
                    Ready-made caption used for every Reel from this publish.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void fetchCopyPoolCaption()}
                    disabled={loadingCaption}
                    className="rounded-lg border border-[#e1e2ed] px-3 py-1.5 text-xs font-semibold text-[#434655] hover:border-[#004ac6] hover:text-[#004ac6] disabled:opacity-50"
                  >
                    {loadingCaption ? "Loading…" : publishDescription ? "Refresh" : "Get caption"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void fetchCopyPoolCaption({ skipCurrent: true })}
                    disabled={loadingCaption || !copyPoolCaptionId}
                    className="rounded-lg border border-[#e1e2ed] px-3 py-1.5 text-xs font-semibold text-[#434655] hover:border-[#004ac6] hover:text-[#004ac6] disabled:opacity-50"
                  >
                    Skip / next
                  </button>
                </div>
              </div>
              {publishDescription ? (
                <p className="text-sm text-[#434655] whitespace-pre-wrap">{publishDescription}</p>
              ) : (
                <p className="text-sm text-[#737686]">
                  {loadingCaption
                    ? "Fetching a caption from the copy pool…"
                    : "No caption yet. Click Get caption, or write one in the form below."}
                </p>
              )}
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handlePublishAllInstagram}
                  disabled={
                    publishingAll ||
                    publishingSelected ||
                    retryingFailed ||
                    Boolean(publishProgress?.active) ||
                    !connectedAccounts.instagram ||
                    !effectiveCaption ||
                    recommendedClips.length === 0
                  }
                  className="rounded-lg bg-gradient-to-r from-pink-500 to-purple-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {publishingAll
                    ? "Queuing…"
                    : publishProgress?.active
                      ? "Publishing…"
                      : `Publish recommended (${recommendedClips.length})`}
                </button>
                <button
                  type="button"
                  onClick={handlePublishSelectedInstagram}
                  disabled={
                    publishingAll ||
                    publishingSelected ||
                    retryingFailed ||
                    Boolean(publishProgress?.active) ||
                    !connectedAccounts.instagram ||
                    !effectiveCaption ||
                    checkedClipIds.length === 0
                  }
                  className="rounded-lg border border-pink-300 bg-pink-50 px-3 py-1.5 text-xs font-semibold text-pink-800 hover:bg-pink-100 disabled:opacity-50"
                >
                  {publishingSelected
                    ? "Queuing…"
                    : `Publish selected (${checkedClipIds.length})`}
                </button>
                {failedPublishCount > 0 && (
                  <button
                    type="button"
                    onClick={handleRetryFailedInstagram}
                    disabled={
                      retryingFailed ||
                      publishingAll ||
                      publishingSelected ||
                      Boolean(publishProgress?.active)
                    }
                    className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-50"
                  >
                    {retryingFailed ? "Retrying…" : `Retry ${failedPublishCount} failed`}
                  </button>
                )}
              </div>

              {publishProgress && (publishProgress.publishable > 0 || progressDone > 0) && (
                <div className="mt-4 rounded-lg border border-[#e1e2ed] bg-[#f7f8fc] px-3 py-3">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-[11px] font-semibold uppercase tracking-wide text-[#737686]">
                    <span>Instagram publish progress</span>
                    <span>
                      {publishProgress.published} published
                      {publishProgress.error > 0 ? ` · ${publishProgress.error} failed` : ""}
                      {publishProgress.in_flight > 0
                        ? ` · ${publishProgress.in_flight} in flight`
                        : ""}
                    </span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-white">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-pink-500 to-purple-600 transition-all duration-500"
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                  {publishProgress.active && (
                    <p className="mt-2 text-[11px] text-[#737686] animate-pulse">
                      Publishing Reels sequentially — stay on this page to watch progress.
                    </p>
                  )}
                </div>
              )}
            </section>

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
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-base font-semibold">Select clips</h2>
                    <div className="flex flex-wrap gap-1.5">
                      <button
                        type="button"
                        onClick={() => setClipListMode("recommended")}
                        className={`rounded-md px-2 py-1 text-[10px] font-semibold ${
                          clipListMode === "recommended"
                            ? "bg-[#004ac6] text-white"
                            : "bg-[#ededf9] text-[#434655]"
                        }`}
                      >
                        Recommended first
                      </button>
                      <button
                        type="button"
                        onClick={() => setClipListMode("chronological")}
                        className={`rounded-md px-2 py-1 text-[10px] font-semibold ${
                          clipListMode === "chronological"
                            ? "bg-[#004ac6] text-white"
                            : "bg-[#ededf9] text-[#434655]"
                        }`}
                      >
                        Chronological
                      </button>
                    </div>
                  </div>
                  <div className="mb-3 flex flex-wrap gap-1.5">
                    <button
                      type="button"
                      onClick={selectRecommendedClips}
                      className="rounded-md border border-[#e1e2ed] px-2 py-1 text-[10px] font-semibold text-[#434655] hover:border-[#004ac6]"
                    >
                      Select recommended
                    </button>
                    <button
                      type="button"
                      onClick={selectAllClips}
                      className="rounded-md border border-[#e1e2ed] px-2 py-1 text-[10px] font-semibold text-[#434655] hover:border-[#004ac6]"
                    >
                      Select all
                    </button>
                    <button
                      type="button"
                      onClick={clearCheckedClips}
                      className="rounded-md border border-[#e1e2ed] px-2 py-1 text-[10px] font-semibold text-[#434655] hover:border-[#004ac6]"
                    >
                      Clear
                    </button>
                  </div>
                  <div className="space-y-3">
                    {displayedClips.map((clip) => {
                      const clipId = clipIdOf(clip)
                      const isFocused = clipId === selectedClipId
                      const isChecked = checkedClipIds.includes(clipId)
                      const ytStatus = getPublishStatus(clipId, "youtube")
                      const igStatus = getPublishStatus(clipId, "instagram")
                      const scoreLabel =
                        typeof clip.interest_score === "number"
                          ? Math.round(clip.interest_score)
                          : null

                      return (
                        <div
                          key={clipId}
                          className={`w-full rounded-xl border p-3 transition-all ${
                            isFocused
                              ? "border-[#004ac6] bg-white shadow-md ring-2 ring-[#004ac6]/20"
                              : "border-[#e1e2ed] bg-white hover:border-[#004ac6]/40 hover:shadow-sm"
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => toggleCheckedClip(clipId)}
                              onClick={(e) => e.stopPropagation()}
                              className="h-4 w-4 rounded border-[#c3c6d7] text-[#004ac6]"
                              aria-label={`Select ${clip.label || clipId}`}
                            />
                            <button
                              type="button"
                              onClick={() => setSelectedClipId(clipId)}
                              className="flex min-w-0 flex-1 items-center gap-3 text-left"
                            >
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
                                  {clip.is_recommended && (
                                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700">
                                      Recommended
                                    </span>
                                  )}
                                  {scoreLabel !== null && (
                                    <span className="rounded-full bg-[#ededf9] px-2 py-0.5 text-[10px] font-semibold text-[#434655]">
                                      Score {scoreLabel}
                                    </span>
                                  )}
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
                            </button>
                          </div>
                        </div>
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
                        Title {selectedPlatform === "youtube" && <span className="text-red-500">*</span>}
                      </label>
                      <input
                        value={publishTitle}
                        onChange={(e) => setPublishTitle(e.target.value)}
                        placeholder={selectedClip?.label || projectTitle || "Enter a catchy title..."}
                        maxLength={100}
                        className="w-full rounded-lg border border-[#d4d7e8] px-3 py-2 text-sm outline-none focus:border-[#004ac6]"
                      />
                    </div>

                    <div className="mb-6">
                      <label className="mb-1.5 block text-xs font-medium uppercase text-[#737686]">
                        Description / Instagram bio
                      </label>
                      <textarea
                        value={publishDescription}
                        onChange={(e) => {
                          setPublishDescription(e.target.value)
                          setCopyPoolCaptionId(null)
                        }}
                        rows={4}
                        maxLength={2200}
                        placeholder="Fetch a ready-made caption, or write your own Instagram caption..."
                        className="w-full rounded-lg border border-[#d4d7e8] px-3 py-2 text-sm outline-none focus:border-[#004ac6]"
                      />
                      <div className="mt-2 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => void fetchCopyPoolCaption()}
                          disabled={loadingCaption}
                          className="rounded-lg border border-[#e1e2ed] px-3 py-1.5 text-xs font-semibold text-[#434655] hover:border-[#004ac6] hover:text-[#004ac6] disabled:opacity-50"
                        >
                          {loadingCaption ? "Loading…" : "Get caption"}
                        </button>
                        <button
                          type="button"
                          onClick={() => void fetchCopyPoolCaption({ skipCurrent: true })}
                          disabled={loadingCaption || !copyPoolCaptionId}
                          className="rounded-lg border border-[#e1e2ed] px-3 py-1.5 text-xs font-semibold text-[#434655] hover:border-[#004ac6] hover:text-[#004ac6] disabled:opacity-50"
                        >
                          Skip / next
                        </button>
                      </div>
                      <p className="mt-1 text-[11px] text-[#737686]">
                        Part numbers are added automatically on Instagram.
                      </p>
                    </div>

                    <button
                      type="button"
                      onClick={handlePublish}
                      disabled={
                        isPublishing ||
                        !selectedClipId ||
                        (selectedPlatform === "youtube" && !publishTitle.trim()) ||
                        (selectedPlatform === "instagram" && !effectiveCaption) ||
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

                  <section className="rounded-xl border border-dashed border-[#c3c6d7] bg-white p-4 shadow-sm">
                    <button
                      type="button"
                      onClick={() => setShowClipDistribute((prev) => !prev)}
                      className="flex w-full items-center justify-between text-left"
                    >
                      <div>
                        <h2 className="text-sm font-semibold text-[#737686]">Advanced: clip file-host upload</h2>
                        <p className="mt-0.5 text-[11px] text-[#737686]">
                          Not needed for the main flow — full movies are already hosted by quality above.
                          Clips should go to Instagram/YouTube only.
                        </p>
                      </div>
                      <span className="text-xs font-semibold text-[#004ac6]">
                        {showClipDistribute ? "Hide" : "Show"}
                      </span>
                    </button>

                    {showClipDistribute && (
                      <div className="mt-4 border-t border-[#e1e2ed] pt-4">
                        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                          <p className="text-xs text-[#737686]">
                            Legacy: upload a single clip to hosts by size bracket.
                          </p>
                          {recommendations && (
                            <button
                              type="button"
                              onClick={applyRecommendedHosts}
                              disabled={distributing || selectionMatchesRecommended}
                              className="rounded-lg border border-[#d4d7e8] px-3 py-1.5 text-xs font-medium text-[#004ac6] hover:bg-[#f0f5ff] disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              Use recommended
                            </button>
                          )}
                        </div>

                        {(selectedClipSizeBytes || recommendations) && (
                          <div className="mb-4 rounded-lg border border-[#e8eaf5] bg-[#f7f8fc] px-3 py-2.5 text-xs text-[#434655]">
                            {loadingRecommendations ? (
                              "Loading size recommendations…"
                            ) : recommendations ? (
                              <>
                                <span className="font-semibold">{formatBytes(selectedClipSizeBytes)}</span>
                                <span className="mx-1.5 text-[#737686]">·</span>
                                <span>
                                  {recommendations.bracket.name} ({recommendations.bracket.label})
                                </span>
                              </>
                            ) : (
                              <>Clip size: {formatBytes(selectedClipSizeBytes)}</>
                            )}
                          </div>
                        )}

                        <div className="mb-4 space-y-2">
                          {displayHosts.map((host) => {
                            const checked = selectedHosts.includes(host.key)
                            const existing = selectedClip?.host_uploads?.[host.key]
                            return (
                              <label
                                key={host.key}
                                className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 ${
                                  host.configured
                                    ? "border-[#e1e2ed] bg-white"
                                    : "border-[#ececf5] bg-[#f7f8fc] opacity-70"
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
                                  <span className="text-sm font-medium">{host.label}</span>
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
                          {distributing ? "Uploading to hosts…" : "Upload clip to selected hosts"}
                        </button>
                      </div>
                    )}
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
