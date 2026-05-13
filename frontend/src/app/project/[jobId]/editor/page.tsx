"use client"

import { useEffect, useRef, useState, useCallback } from "react"
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

type CaptionItem = {
  id?: string
  _id?: string
  clip_id?: string | null
  raw_text?: string
  created_at?: string
  updated_at?: string
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

type AssetResult = {
  source_id: string
  source: "pexels" | "pixabay"
  asset_type: "image" | "video"
  url: string
  thumbnail_url?: string | null
  photographer?: string | null
}

type SidePanel = "captions" | "broll" | "templates"
type ClipDuration = 30 | 60
type FontEntry = { label: string; family: string }
type LeftTool = "media" | "canvas" | "text" | "audio" | "videos" | "images" | "elements" | "record" | "tts"
type TopTab = "transform" | "adjust" | "audio" | "speed" | "time"

// ── Font data ──────────────────────────────────────────────────────────────
const FONT_CATEGORIES: { label: string; fonts: FontEntry[] }[] = [
  {
    label: "🔥 Bold & Impact",
    fonts: [
      { label: "Bebas Neue", family: "'Bebas Neue', cursive" },
      { label: "Anton", family: "'Anton', sans-serif" },
      { label: "Archivo Black", family: "'Archivo Black', sans-serif" },
      { label: "Oswald", family: "'Oswald', sans-serif" },
      { label: "Russo One", family: "'Russo One', sans-serif" },
      { label: "Bangers", family: "'Bangers', cursive" },
    ],
  },
  {
    label: "✨ Clean & Modern",
    fonts: [
      { label: "Poppins", family: "'Poppins', sans-serif" },
      { label: "Montserrat", family: "'Montserrat', sans-serif" },
      { label: "Nunito", family: "'Nunito', sans-serif" },
      { label: "DM Sans", family: "'DM Sans', sans-serif" },
      { label: "Outfit", family: "'Outfit', sans-serif" },
    ],
  },
  {
    label: "🚀 Techy & Futuristic",
    fonts: [
      { label: "Orbitron", family: "'Orbitron', sans-serif" },
      { label: "Rajdhani", family: "'Rajdhani', sans-serif" },
      { label: "Audiowide", family: "'Audiowide', cursive" },
      { label: "Exo 2", family: "'Exo 2', sans-serif" },
    ],
  },
  {
    label: "✍️ Handwritten & Fun",
    fonts: [
      { label: "Pacifico", family: "'Pacifico', cursive" },
      { label: "Caveat", family: "'Caveat', cursive" },
      { label: "Dancing Script", family: "'Dancing Script', cursive" },
      { label: "Permanent Marker", family: "'Permanent Marker', cursive" },
    ],
  },
  {
    label: "📖 Elegant & Serif",
    fonts: [
      { label: "Playfair Display", family: "'Playfair Display', serif" },
      { label: "Lora", family: "'Lora', serif" },
      { label: "Merriweather", family: "'Merriweather', serif" },
      { label: "Cinzel", family: "'Cinzel', serif" },
    ],
  },
]
const ALL_FONTS: FontEntry[] = FONT_CATEGORIES.flatMap((c) => c.fonts)

const TEMPLATES = [
  { key: "podcast", label: "Podcast", description: "Speaker focused, lower-third captions", icon: "🎙️" },
  { key: "interview", label: "Interview", description: "Two-speaker, dynamic captions", icon: "🎤" },
  { key: "tutorial", label: "Tutorial", description: "Screen + face pip, step highlights", icon: "📚" },
  { key: "vlog", label: "Vlog", description: "Fast pacing, energetic caption style", icon: "🎬" },
]

// ── Helpers ────────────────────────────────────────────────────────────────
function formatTime(s: number) {
  if (!s || s < 0) return "0:00"
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, "0")}`
}

function TrashIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  )
}

// ── Left sidebar icons ─────────────────────────────────────────────────────
const LEFT_TOOLS: { key: LeftTool; label: string; icon: React.ReactNode }[] = [
  { key: "media", label: "Media", icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg> },
  { key: "canvas", label: "Canvas", icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" strokeWidth={1.8} /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M3 9h18M9 21V9" /></svg> },
  { key: "text", label: "Text", icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M4 6h16M4 12h16M4 18h7" /></svg> },
  { key: "audio", label: "Audio", icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2z" /></svg> },
  { key: "videos", label: "Videos", icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" /></svg> },
  { key: "images", label: "Images", icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg> },
  { key: "elements", label: "Elements", icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" /></svg> },
  { key: "record", label: "Record", icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4" strokeWidth={1.8} /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 1v3m0 16v3M4.22 4.22l2.12 2.12m11.32 11.32l2.12 2.12M1 12h3m16 0h3M4.22 19.78l2.12-2.12M18.66 5.34l2.12-2.12" /></svg> },
  { key: "tts", label: "TTS", icon: <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2z" /></svg> },
]

const TOP_TABS: { key: TopTab; label: string }[] = [
  { key: "transform", label: "Transform" },
  { key: "adjust", label: "Adjust" },
  { key: "audio", label: "Audio" },
  { key: "speed", label: "Speed" },
  { key: "time", label: "Time" },
]

// ── Sub-panels ─────────────────────────────────────────────────────────────
function TransformPanel() {
  const [rotation, setRotation] = useState(0)
  const [flipH, setFlipH] = useState(false)
  const [flipV, setFlipV] = useState(false)
  const [fitMode, setFitMode] = useState<"fill" | "fit" | "crop">("fit")
  return (
    <div className="p-4 space-y-5">
      <div className="grid grid-cols-3 gap-3">
        {(["fill", "fit", "crop"] as const).map((m) => (
          <button key={m} onClick={() => setFitMode(m)}
            className={`flex flex-col items-center gap-1.5 rounded-xl border py-3 text-xs font-semibold transition-all ${fitMode === m ? "border-[#1a73e8] bg-[#1a73e8]/10 text-[#1a73e8]" : "border-slate-200 bg-slate-100 text-slate-500 hover:border-slate-300"}`}>
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {m === "fill" && <rect x="3" y="3" width="18" height="18" rx="1" strokeWidth={1.8} fill="currentColor" opacity="0.3" />}
              {m === "fit" && <><rect x="3" y="3" width="18" height="18" rx="1" strokeWidth={1.8} /><rect x="6" y="6" width="12" height="12" rx="1" strokeWidth={1.8} /></>}
              {m === "crop" && <><rect x="3" y="3" width="18" height="18" rx="1" strokeWidth={1.8} /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 3v18M3 9h18" /></>}
            </svg>
            {m.charAt(0).toUpperCase() + m.slice(1)}
          </button>
        ))}
      </div>
      <div>
        <p className="text-[11px] uppercase font-semibold text-slate-600 mb-3">Flip & Rotate</p>
        <div className="flex items-center gap-2">
          <button onClick={() => setFlipH(p => !p)} className={`flex items-center justify-center w-9 h-9 rounded-lg border transition-all ${flipH ? "border-[#1a73e8] bg-[#1a73e8]/10 text-[#1a73e8]" : "border-slate-200 bg-slate-100 text-slate-500 hover:border-slate-300"}`}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 3H5a2 2 0 00-2 2v14a2 2 0 002 2h3m8-18h3a2 2 0 012 2v14a2 2 0 01-2 2h-3m-4-18v18" /></svg>
          </button>
          <button onClick={() => setFlipV(p => !p)} className={`flex items-center justify-center w-9 h-9 rounded-lg border transition-all ${flipV ? "border-[#1a73e8] bg-[#1a73e8]/10 text-[#1a73e8]" : "border-slate-200 bg-slate-100 text-slate-500 hover:border-slate-300"}`}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8V5a2 2 0 012-2h14a2 2 0 012 2v3m-18 8v3a2 2 0 002 2h14a2 2 0 002-2v-3m-18-4h18" /></svg>
          </button>
          <button onClick={() => setRotation(r => (r - 90 + 360) % 360)} className="flex items-center justify-center w-9 h-9 rounded-lg border border-slate-200 bg-slate-100 text-slate-500 hover:border-slate-300 transition-all">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
          </button>
          <button onClick={() => setRotation(r => Math.max(r - 1, 0))} className="flex items-center justify-center w-9 h-9 rounded-lg border border-slate-200 bg-slate-100 text-slate-500 hover:border-slate-300 transition-all text-sm font-bold">−</button>
          <span className="w-12 text-center text-xs font-mono text-slate-500 bg-slate-100 border border-slate-200 rounded-lg py-2">{rotation}°</span>
          <button onClick={() => setRotation(r => Math.min(r + 1, 360))} className="flex items-center justify-center w-9 h-9 rounded-lg border border-slate-200 bg-slate-100 text-slate-500 hover:border-slate-300 transition-all text-sm font-bold">+</button>
        </div>
      </div>
    </div>
  )
}

function AdjustPanel() {
  const [brightness, setBrightness] = useState(100)
  const [contrast, setContrast] = useState(100)
  const [saturation, setSaturation] = useState(100)
  const sliders = [
    { label: "Brightness", value: brightness, set: setBrightness, min: 0, max: 200 },
    { label: "Contrast", value: contrast, set: setContrast, min: 0, max: 200 },
    { label: "Saturation", value: saturation, set: setSaturation, min: 0, max: 200 },
  ]
  return (
    <div className="p-4 space-y-4">
      {sliders.map(s => (
        <div key={s.label}>
          <div className="flex justify-between mb-1.5">
            <span className="text-xs text-slate-500">{s.label}</span>
            <span className="text-xs font-mono text-slate-500">{s.value}</span>
          </div>
          <input type="range" min={s.min} max={s.max} value={s.value} onChange={e => s.set(Number(e.target.value))}
            className="w-full h-1.5 rounded-full appearance-none bg-[#3a3a3a] accent-[#1a73e8]" />
        </div>
      ))}
    </div>
  )
}

function SpeedPanel() {
  const [speed, setSpeed] = useState(1)
  const speeds = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2]
  return (
    <div className="p-4 space-y-4">
      <p className="text-[11px] uppercase font-semibold text-slate-600">Playback Speed</p>
      <div className="grid grid-cols-4 gap-2">
        {speeds.map(s => (
          <button key={s} onClick={() => setSpeed(s)}
            className={`rounded-lg py-2 text-xs font-semibold transition-all ${speed === s ? "bg-[#1a73e8] text-white" : "bg-slate-100 border border-slate-200 text-slate-500 hover:border-slate-300"}`}>
            {s}x
          </button>
        ))}
      </div>
    </div>
  )
}

function AudioPanel() {
  const [volume, setVolume] = useState(100)
  const [muted, setMuted] = useState(false)
  return (
    <div className="p-4 space-y-4">
      <div>
        <div className="flex justify-between mb-1.5">
          <span className="text-xs text-slate-500">Volume</span>
          <span className="text-xs font-mono text-slate-500">{muted ? "Muted" : `${volume}%`}</span>
        </div>
        <input type="range" min={0} max={100} value={muted ? 0 : volume} onChange={e => setVolume(Number(e.target.value))}
          className="w-full h-1.5 rounded-full appearance-none bg-[#3a3a3a] accent-[#1a73e8]" />
      </div>
      <button onClick={() => setMuted(p => !p)}
        className={`w-full py-2 rounded-lg text-xs font-semibold border transition-all ${muted ? "border-red-500 bg-red-500/10 text-red-400" : "border-slate-200 bg-slate-100 text-slate-500 hover:border-slate-300"}`}>
        {muted ? "🔇 Unmute" : "🔊 Mute"}
      </button>
    </div>
  )
}

function TimePanel({ duration }: { duration: number }) {
  return (
    <div className="p-4 space-y-3">
      <p className="text-[11px] uppercase font-semibold text-slate-600">Video Info</p>
      <div className="space-y-2">
        <div className="flex justify-between rounded-lg bg-slate-100 px-3 py-2">
          <span className="text-xs text-slate-600">Total Duration</span>
          <span className="text-xs font-mono text-slate-500">{formatTime(duration)}</span>
        </div>
        <div className="flex justify-between rounded-lg bg-slate-100 px-3 py-2">
          <span className="text-xs text-slate-600">Frame Rate</span>
          <span className="text-xs font-mono text-slate-500">30 fps</span>
        </div>
      </div>
    </div>
  )
}

// ── Main Editor Component ──────────────────────────────────────────────────
export default function ClideoEditor() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.jobId as string

  const videoRef = useRef<HTMLVideoElement>(null)
  const timelineRef = useRef<HTMLDivElement>(null)
  const selBoxRef = useRef<HTMLDivElement>(null)
  const fontPickerRef = useRef<HTMLDivElement>(null)

  // Project state
  const [project, setProject] = useState<ProjectData | null>(null)
  const [clips, setClips] = useState<ClipData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // ── FIX: token read client-side only ──
  const [token, setToken] = useState("")
  useEffect(() => {
    setToken(localStorage.getItem("token") || "")
  }, [])

  // Video state
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [videoError, setVideoError] = useState<string | null>(null)

  // Selection box
  const [clipDuration, setClipDuration] = useState<ClipDuration>(30)
  const [selStart, setSelStart] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const [dragStartX, setDragStartX] = useState(0)
  const [dragStartSel, setDragStartSel] = useState(0)
  const [isCreatingClip, setIsCreatingClip] = useState(false)
  const [createSuccess, setCreateSuccess] = useState(false)

  // UI state
  const [activeTool, setActiveTool] = useState<LeftTool>("media")
  const [activeTab, setActiveTab] = useState<TopTab>("transform")
  const [sidePanel, setSidePanel] = useState<SidePanel>("captions")
  const [rightPanelOpen, setRightPanelOpen] = useState(true)

  // Captions
  const [captions, setCaptions] = useState<CaptionItem[]>([])
  const [captionText, setCaptionText] = useState("")
  const [isSavingCaption, setIsSavingCaption] = useState(false)
  const [selectedCaptionClipId, setSelectedCaptionClipId] = useState("")
  const [editingCaptionId, setEditingCaptionId] = useState<string | null>(null)
  const [editingText, setEditingText] = useState("")
  const [selectedFont, setSelectedFont] = useState<FontEntry>(ALL_FONTS[0])
  const [showFontPicker, setShowFontPicker] = useState(false)
  const [fontSearch, setFontSearch] = useState("")

  // B-roll
  const [searchQuery, setSearchQuery] = useState("")
  const [searchSource, setSearchSource] = useState<"all" | "pexels" | "pixabay">("all")
  const [searchResults, setSearchResults] = useState<AssetResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [savedAssets, setSavedAssets] = useState<SavedAsset[]>([])
  const [savingAssetId, setSavingAssetId] = useState<string | null>(null)
  const [showGallery, setShowGallery] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  // ── Gallery delete/select (RESTORED) ──
  const [isSelectMode, setIsSelectMode] = useState(false)
  const [selectedAssetIds, setSelectedAssetIds] = useState<Set<string>>(new Set())
  const [isDeletingSelected, setIsDeletingSelected] = useState(false)
  const [deletingAssetId, setDeletingAssetId] = useState<string | null>(null)

  // Templates
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null)

  // ── Load project ──
  const loadProject = useCallback(async () => {
    try {
      const [projRes, clipsRes] = await Promise.all([
        api.get(`/api/v1/projects/${projectId}`),
        api.get(`/api/v1/projects/${projectId}/clips`),
      ])
      setProject(projRes.data)
      setClips(Array.isArray(clipsRes.data) ? clipsRes.data : [])
    } catch { setError("Could not load project.") }
    finally { setLoading(false) }
  }, [projectId])

  const loadCaptions = useCallback(async () => {
    try {
      const r = await api.get(`/api/v1/projects/${projectId}/captions`)
      setCaptions(Array.isArray(r.data) ? r.data : [])
    } catch { /* non-blocking */ }
  }, [projectId])

  const loadSavedAssets = useCallback(async () => {
    try {
      const r = await api.get(`/api/v1/projects/${projectId}/assets`)
      setSavedAssets(Array.isArray(r.data) ? r.data : [])
    } catch { /* non-blocking */ }
  }, [projectId])

  useEffect(() => {
    const t = localStorage.getItem("token")
    if (!t) { router.push("/login"); return }
    if (!projectId || projectId === "undefined") { router.push("/dashboard"); return }
    loadProject()
    loadCaptions()
    loadSavedAssets()
  }, [loadProject, loadCaptions, loadSavedAssets, router, projectId])

  // Font picker outside click
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (fontPickerRef.current && !fontPickerRef.current.contains(e.target as Node)) setShowFontPicker(false)
    }
    document.addEventListener("mousedown", h)
    return () => document.removeEventListener("mousedown", h)
  }, [])

  // ── Video handlers ──
  const handleLoadedMetadata = () => {
    if (!videoRef.current) return
    setDuration(videoRef.current.duration)
    setSelStart(0)
    setVideoError(null)
  }

  const handleTimeUpdate = () => {
    if (videoRef.current) setCurrentTime(videoRef.current.currentTime)
  }

  const handleVideoError = () => {
    setVideoError("Could not load video. Check that the backend is running and the project is ready.")
  }

  const handlePlayPause = () => {
    if (!videoRef.current) return
    if (videoRef.current.paused) { videoRef.current.play(); setIsPlaying(true) }
    else { videoRef.current.pause(); setIsPlaying(false) }
  }

  const handleSkip = (dir: -1 | 1) => {
    if (!videoRef.current) return
    videoRef.current.currentTime = Math.max(0, Math.min(duration, videoRef.current.currentTime + dir * 5))
  }

  // Timeline click
  const handleTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!timelineRef.current || duration === 0) return
    const rect = timelineRef.current.getBoundingClientRect()
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    if (videoRef.current) videoRef.current.currentTime = pct * duration
  }

  // Selection box drag
  const handleSelBoxMouseDown = (e: React.MouseEvent) => {
    e.stopPropagation()
    setIsDragging(true)
    setDragStartX(e.clientX)
    setDragStartSel(selStart)
  }

  useEffect(() => {
    if (!isDragging) return
    const onMove = (e: MouseEvent) => {
      if (!timelineRef.current || duration === 0) return
      const rect = timelineRef.current.getBoundingClientRect()
      const delta = ((e.clientX - dragStartX) / rect.width) * duration
      let newStart = dragStartSel + delta
      newStart = Math.max(0, Math.min(newStart, duration - clipDuration))
      setSelStart(newStart)
    }
    const onUp = () => setIsDragging(false)
    document.addEventListener("mousemove", onMove)
    document.addEventListener("mouseup", onUp)
    return () => { document.removeEventListener("mousemove", onMove); document.removeEventListener("mouseup", onUp) }
  }, [isDragging, dragStartX, dragStartSel, duration, clipDuration])

  // Create clip
  const handleCreateClip = async () => {
    setIsCreatingClip(true)
    try {
      await api.post(`/api/v1/projects/${projectId}/clips`, {
        start_time: Math.round(selStart),
        end_time: Math.round(selStart + clipDuration),
        clip_type: `${clipDuration}s`,
      })
      await loadProject()
      setCreateSuccess(true)
      setTimeout(() => setCreateSuccess(false), 2500)
    } catch { setError("Could not create clip.") }
    finally { setIsCreatingClip(false) }
  }

  const handleSplit = () => {
    if (currentTime > selStart && currentTime < selStart + clipDuration) {
      setSelStart(currentTime)
    }
  }

  // Caption handlers
  const handleSaveCaption = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!captionText.trim()) return
    setIsSavingCaption(true)
    try {
      await api.post(`/api/v1/projects/${projectId}/captions`, { raw_text: captionText.trim(), clip_id: selectedCaptionClipId || null })
      setCaptionText("")
      await loadCaptions()
    } catch { setError("Could not save caption.") }
    finally { setIsSavingCaption(false) }
  }

  const handleUpdateCaption = async (id: string) => {
    if (!editingText.trim()) return
    try {
      await api.patch(`/api/v1/captions/${id}`, { raw_text: editingText.trim() })
      setEditingCaptionId(null); setEditingText("")
      await loadCaptions()
    } catch { setError("Could not update caption.") }
  }

  const handleDeleteCaption = async (id: string) => {
    try { await api.delete(`/api/v1/captions/${id}`); await loadCaptions() }
    catch { setError("Could not delete caption.") }
  }

  // B-roll handlers
  const handleSearchAssets = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!searchQuery.trim()) return
    setIsSearching(true)
    try {
      const r = await api.get("/api/v1/assets/search", { params: { q: searchQuery.trim(), type: "image", source: searchSource, per_page: 18 } })
      setSearchResults(Array.isArray(r.data?.results) ? r.data.results : [])
    } catch { setError("Could not search assets.") }
    finally { setIsSearching(false) }
  }

  const handleSaveAsset = async (asset: AssetResult) => {
    setSavingAssetId(asset.source_id); setSaveMessage(null)
    try {
      const r = await api.post(`/api/v1/projects/${projectId}/assets`, {
        source_id: asset.source_id, source: asset.source, asset_type: asset.asset_type,
        url: asset.url, thumbnail_url: asset.thumbnail_url, query_used: searchQuery.trim(), photographer: asset.photographer,
      })
      setSaveMessage("Saved!")
      setSavedAssets(prev => [r.data as SavedAsset, ...prev])
      setTimeout(() => setSaveMessage(null), 2000)
    } catch (err: unknown) {
      const s = (err as { response?: { status?: number } })?.response?.status
      if (s === 409) window.alert("Already saved.")
      else setError("Could not save asset.")
    } finally { setSavingAssetId(null) }
  }

  // ── Gallery delete/select handlers (RESTORED) ──
  const toggleAssetSelection = (assetId: string) => {
    setSelectedAssetIds(prev => {
      const next = new Set(prev)
      if (next.has(assetId)) next.delete(assetId)
      else next.add(assetId)
      return next
    })
  }

  const handleSelectAll = () => {
    const allIds = new Set(savedAssets.map(a => a.id || a._id || "").filter(Boolean))
    if (selectedAssetIds.size === allIds.size) setSelectedAssetIds(new Set())
    else setSelectedAssetIds(allIds)
  }

  const handleDeleteSingleAsset = async (assetId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!window.confirm("Delete this image?")) return
    setDeletingAssetId(assetId)
    try {
      await api.delete(`/api/v1/assets/${assetId}`)
      setSavedAssets(prev => prev.filter(a => (a.id || a._id) !== assetId))
    } catch { setError("Could not delete image.") }
    finally { setDeletingAssetId(null) }
  }

  const handleDeleteSelectedAssets = async () => {
    if (selectedAssetIds.size === 0 || isDeletingSelected) return
    if (!window.confirm(`Delete ${selectedAssetIds.size} selected image(s)?`)) return
    setIsDeletingSelected(true)
    try {
      await Promise.all(Array.from(selectedAssetIds).map(id => api.delete(`/api/v1/assets/${id}`)))
      setSavedAssets(prev => prev.filter(a => !selectedAssetIds.has(a.id || a._id || "")))
      setSelectedAssetIds(new Set()); setIsSelectMode(false)
    } catch { setError("Could not delete images.") }
    finally { setIsDeletingSelected(false) }
  }

  // Computed
  const selPctStart = duration > 0 ? (selStart / duration) * 100 : 0
  const selPctWidth = duration > 0 ? (clipDuration / duration) * 100 : 0
  const playheadPct = duration > 0 ? (currentTime / duration) * 100 : 0
  const filteredFonts = fontSearch.trim() ? ALL_FONTS.filter(f => f.label.toLowerCase().includes(fontSearch.toLowerCase())) : null
  const allSelected = savedAssets.length > 0 && selectedAssetIds.size === savedAssets.length

  // ── FIX: only build videoSrc after token is available client-side ──
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  const videoSrc = token
    ? `${apiBase}/api/v1/projects/${projectId}/stream?token=${token}`
    : ""

  const isReady = project?.status?.toLowerCase() === "ready"

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f8fbff]">
        <div className="text-center">
          <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-[#1a73e8] border-t-transparent" />
          <p className="text-sm text-slate-600">Loading editor…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen bg-[#f8fbff] text-slate-900 overflow-hidden" style={{ fontFamily: "'DM Sans', sans-serif" }}>

      {/* ── TOP HEADER ── */}
      <header className="flex items-center justify-between px-4 h-11 border-b border-slate-200 bg-white flex-shrink-0 z-50">
        <div className="flex items-center gap-3">
          <button onClick={() => router.push("/dashboard")} className="text-xs text-slate-600 hover:text-slate-900 transition-colors px-2">← Back</button>
          <div className="w-px h-5 bg-slate-200" />
          <span className="text-xs text-slate-600 truncate max-w-[200px]">{project?.title || "Untitled"}</span>
          <button className="text-slate-600 hover:text-slate-900 transition-colors p-1">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
          </button>
          <button className="text-slate-600 hover:text-slate-900 transition-colors p-1">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" /></svg>
          </button>
        </div>
        <div className="flex items-center gap-2">
          {error && <span className="text-xs text-red-400 mr-2">{error}</span>}
          {createSuccess && <span className="text-xs text-emerald-400 mr-2">✓ Clip created!</span>}
          <button
            onClick={handleCreateClip}
            disabled={isCreatingClip || duration === 0}
            className="flex items-center gap-2 rounded-lg bg-[#1a73e8] px-4 py-1.5 text-xs font-semibold text-white shadow hover:bg-[#1557b0] disabled:opacity-50 transition-all"
          >
            {isCreatingClip ? "Creating…" : "Create Clip"}
          </button>
        </div>
      </header>

      {/* ── BODY ── */}
      <div className="flex flex-1 min-h-0">

        {/* LEFT SIDEBAR */}
        <aside className="flex flex-col w-[60px] border-r border-slate-200 bg-white flex-shrink-0">
          <div className="flex justify-center py-3 border-b border-slate-200">
            <button className="flex items-center justify-center w-9 h-9 rounded-full bg-[#1a73e8] hover:bg-[#1557b0] transition-colors shadow-lg">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" /></svg>
            </button>
          </div>
          <nav className="flex flex-col items-center gap-0.5 py-2 flex-1 overflow-y-auto">
            {LEFT_TOOLS.map(t => (
              <button key={t.key} onClick={() => setActiveTool(t.key)} title={t.label}
                className={`flex flex-col items-center gap-0.5 w-full py-2 transition-all ${activeTool === t.key ? "text-[#1a73e8]" : "text-slate-600 hover:text-slate-900"}`}>
                {t.icon}
                <span className="text-[9px] font-medium leading-none">{t.label}</span>
              </button>
            ))}
          </nav>
        </aside>

        {/* CENTER */}
        <div className="flex flex-col flex-1 min-w-0">

          {/* Top tabs */}
          <div className="flex items-center gap-1 px-4 border-b border-slate-200 bg-white flex-shrink-0 h-10">
            {TOP_TABS.map(tab => (
              <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                className={`px-3 py-1 text-xs font-semibold rounded transition-colors ${activeTab === tab.key ? "text-slate-900 bg-slate-100" : "text-slate-600 hover:text-slate-900"}`}>
                {tab.label}
              </button>
            ))}
            <div className="flex-1" />
            <span className="text-[10px] text-slate-600 truncate max-w-[150px]">{project?.title?.slice(0, 40) || "Untitled"}</span>
          </div>

          <div className="flex flex-1 min-h-0">
            {/* Sub-panel */}
            <div className="w-[220px] border-r border-slate-200 bg-white overflow-y-auto flex-shrink-0">
              {activeTab === "transform" && <TransformPanel />}
              {activeTab === "adjust" && <AdjustPanel />}
              {activeTab === "audio" && <AudioPanel />}
              {activeTab === "speed" && <SpeedPanel />}
              {activeTab === "time" && <TimePanel duration={duration} />}
            </div>

            {/* Video Preview */}
            <div className="flex-1 flex items-center justify-center bg-slate-100 p-4">
              {/* ── FIX: show video when ready and token available, else appropriate message ── */}
              {isReady && videoSrc ? (
                <div className="relative w-full h-full flex items-center justify-center">
                  <video
                    ref={videoRef}
                    src={videoSrc}
                    onLoadedMetadata={handleLoadedMetadata}
                    onTimeUpdate={handleTimeUpdate}
                    onPlay={() => setIsPlaying(true)}
                    onPause={() => setIsPlaying(false)}
                    onError={handleVideoError}
                    className="max-w-full max-h-full rounded-lg shadow-2xl"
                    style={{ maxHeight: "calc(100% - 16px)" }}
                  />
                  {videoError && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900/70 rounded-lg">
                      <p className="text-sm text-red-400 text-center px-4">{videoError}</p>
                      <p className="text-xs text-slate-600 mt-2">Make sure backend is running at {apiBase}</p>
                    </div>
                  )}
                </div>
              ) : !isReady ? (
                <div className="flex flex-col items-center gap-3 text-slate-600">
                  <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" /></svg>
                  <p className="text-sm">Video not ready — status: {project?.status || "unknown"}</p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3 text-slate-600">
                  <div className="h-8 w-8 animate-spin rounded-full border-4 border-[#1a73e8] border-t-transparent" />
                  <p className="text-sm">Loading video…</p>
                </div>
              )}
            </div>
          </div>

          {/* ── TIMELINE ── */}
          <div className="flex-shrink-0 border-t border-slate-200 bg-white">
            {/* Toolbar */}
            <div className="flex items-center justify-between px-4 h-10 border-b border-slate-200 bg-white">
              <div className="flex items-center gap-1">
                <button title="Cut" className="flex items-center justify-center w-7 h-7 rounded text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-all">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 9l6 6m0 0l6-6m-6 6V3" /></svg>
                </button>
                <button title="Split at playhead" onClick={handleSplit} className="flex items-center justify-center w-7 h-7 rounded text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-all">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h8M8 12h8M8 17h8M3 7h.01M3 12h.01M3 17h.01" /></svg>
                </button>
                <button title="Copy" className="flex items-center justify-center w-7 h-7 rounded text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-all">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                </button>
                <button title="Delete" className="flex items-center justify-center w-7 h-7 rounded text-slate-600 hover:text-red-500 hover:bg-slate-100 transition-all">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
              </div>

              {/* Playback */}
              <div className="flex items-center gap-2">
                <button onClick={() => handleSkip(-1)} className="text-slate-600 hover:text-slate-900 transition-colors">
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z" /></svg>
                </button>
                <button onClick={handlePlayPause} className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 transition-colors">
                  {isPlaying
                    ? <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></svg>
                    : <svg className="w-4 h-4 ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>}
                </button>
                <button onClick={() => handleSkip(1)} className="text-slate-600 hover:text-slate-900 transition-colors">
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 18l8.5-6L6 6v12zm2.5-6l5.5 3.9V8.1L8.5 12zM16 6h2v12h-2z" /></svg>
                </button>
                <span className="text-xs font-mono text-slate-600 ml-2">
                  <span className="text-white">{formatTime(currentTime)}</span>
                  <span className="mx-1">/</span>
                  {formatTime(duration)}
                </span>
              </div>

              {/* Duration selector */}
              <div className="flex items-center gap-2">
                <div className="flex rounded-lg border border-slate-200 overflow-hidden">
                  {([30, 60] as ClipDuration[]).map(d => (
                    <button key={d}
                      onClick={() => { setClipDuration(d); setSelStart(s => Math.min(s, (duration || 999) - d)) }}
                      className={`px-3 py-1 text-xs font-semibold transition-all ${clipDuration === d ? "bg-[#1a73e8] text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
                      {d}s
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Time ruler */}
            <div className="relative h-5 bg-white border-b border-slate-200 select-none">
              {duration > 0 && Array.from({ length: Math.ceil(duration / 5) + 1 }).map((_, i) => {
                const t = i * 5
                const pct = (t / duration) * 100
                if (pct > 100) return null
                return (
                  <div key={i} className="absolute top-0 flex flex-col items-center" style={{ left: `${pct}%` }}>
                    <div className="w-px h-2 bg-[#444]" />
                    <span className="text-[9px] text-slate-600 leading-none mt-0.5">{formatTime(t)}</span>
                  </div>
                )
              })}
            </div>

            {/* Filmstrip */}
            <div ref={timelineRef} onClick={handleTimelineClick}
              className="relative h-16 bg-slate-100 cursor-pointer overflow-hidden"
              style={{ userSelect: "none" }}>
              <div className="absolute inset-0 flex">
                {Array.from({ length: 40 }).map((_, i) => (
                  <div key={i} className="flex-1 border-r border-[#222]">
                    <div className="w-full h-full bg-gradient-to-b from-[#2a2220] to-[#1a1210] opacity-60" />
                  </div>
                ))}
              </div>

              {clips.map(clip => {
                if (!duration) return null
                const cStart = ((clip.start_time || 0) / duration) * 100
                const cWidth = (((clip.end_time || 0) - (clip.start_time || 0)) / duration) * 100
                return (
                  <div key={clip.id || clip._id}
                    className="absolute top-1 bottom-1 rounded bg-[#1a4a8a]/60 border border-[#1a73e8]/50"
                    style={{ left: `${cStart}%`, width: `${cWidth}%` }} />
                )
              })}

              {/* Playhead */}
              <div className="absolute top-0 bottom-0 w-0.5 bg-red-500 pointer-events-none z-20"
                style={{ left: `${playheadPct}%` }}>
                <div className="w-2 h-2 bg-red-500 rounded-full -ml-[3px]" />
              </div>

              {/* Selection box */}
              {duration > 0 && (
                <div ref={selBoxRef} onMouseDown={handleSelBoxMouseDown}
                  className="absolute top-0 bottom-0 z-10 rounded"
                  style={{
                    left: `${selPctStart}%`,
                    width: `${selPctWidth}%`,
                    background: isDragging ? "rgba(255,193,7,0.35)" : "rgba(255,193,7,0.25)",
                    border: "2px solid #ffc107",
                    boxShadow: "0 0 16px rgba(255,193,7,0.3)",
                    cursor: isDragging ? "grabbing" : "grab",
                  }}>
                  <div className="absolute left-0 top-0 bottom-0 w-2 bg-gradient-to-r from-[#ffc107] to-transparent rounded-l" />
                  <div className="absolute right-0 top-0 bottom-0 w-2 bg-gradient-to-l from-[#ffc107] to-transparent rounded-r" />
                  <div className="flex items-center justify-between h-full px-3 pointer-events-none">
                    <span className="text-[10px] font-bold text-black bg-[#ffc107] rounded px-1">{formatTime(selStart)}</span>
                    <span className="text-[9px] font-bold text-black bg-[#ffc107] rounded px-1">{clipDuration}s</span>
                    <span className="text-[10px] font-bold text-black bg-[#ffc107] rounded px-1">{formatTime(selStart + clipDuration)}</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── RIGHT PANEL ── */}
        <div className={`flex flex-col flex-shrink-0 border-l border-slate-200 bg-white transition-all duration-200 ${rightPanelOpen ? "w-[300px]" : "w-[36px]"}`}>
          <div className="flex items-center justify-between px-2 h-10 border-b border-slate-200 flex-shrink-0">
            {rightPanelOpen && (
              <div className="flex flex-1">
                {(["captions", "broll", "templates"] as SidePanel[]).map(panel => (
                  <button key={panel} onClick={() => setSidePanel(panel)}
                    className={`flex-1 text-[11px] font-semibold py-1 transition-colors ${sidePanel === panel ? "text-[#1a73e8] border-b-2 border-[#1a73e8]" : "text-slate-600 hover:text-slate-900"}`}>
                    {panel === "broll" ? "B-Roll" : panel.charAt(0).toUpperCase() + panel.slice(1)}
                  </button>
                ))}
              </div>
            )}
            <button onClick={() => setRightPanelOpen(p => !p)}
              className="flex items-center justify-center w-6 h-6 rounded text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-all ml-auto">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={rightPanelOpen ? "M9 5l7 7-7 7" : "M15 19l-7-7 7-7"} />
              </svg>
            </button>
          </div>

          {rightPanelOpen && (
            <div className="flex-1 overflow-y-auto p-3">

              {/* ── CAPTIONS ── */}
              {sidePanel === "captions" && (
                <div className="space-y-3">
                  <p className="text-[11px] text-slate-600">Add captions and map them to a specific clip.</p>
                  <div ref={fontPickerRef} className="relative">
                    <p className="mb-1 text-[10px] font-semibold uppercase text-slate-600">Caption Font</p>
                    <button onClick={() => setShowFontPicker(p => !p)}
                      className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-slate-100 px-3 py-2 text-xs hover:border-slate-300 transition-colors">
                      <span style={{ fontFamily: selectedFont.family }} className="text-white">{selectedFont.label}</span>
                      <svg className={`w-3.5 h-3.5 text-slate-500 transition-transform ${showFontPicker ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                    </button>
                    {showFontPicker && (
                      <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-64 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-2xl">
                        <div className="sticky top-0 border-b border-slate-200 bg-white p-2">
                          <input autoFocus value={fontSearch} onChange={e => setFontSearch(e.target.value)}
                            placeholder="Search fonts…"
                            className="w-full rounded-lg border border-slate-200 bg-slate-100 px-3 py-1.5 text-xs text-slate-900 outline-none focus:border-[#1a73e8]" />
                        </div>
                        {(filteredFonts || ALL_FONTS).map(font => (
                          <button key={font.label} onClick={() => { setSelectedFont(font); setShowFontPicker(false); setFontSearch("") }}
                            className={`flex w-full items-center justify-between px-3 py-2 text-xs hover:bg-slate-100 ${selectedFont.label === font.label ? "text-[#1a73e8]" : "text-slate-500"}`}>
                            <span style={{ fontFamily: font.family }}>{font.label}</span>
                            <span className="text-[10px] text-slate-600" style={{ fontFamily: font.family }}>Abc</span>
                          </button>
                        ))}
                      </div>
                    )}
                    <div className="mt-2 rounded-lg border border-slate-200 bg-slate-100 px-3 py-2.5 text-center">
                      <p className="text-sm text-white" style={{ fontFamily: selectedFont.family }}>This is how your captions will look</p>
                    </div>
                  </div>

                  <form onSubmit={handleSaveCaption} className="space-y-2">
                    <select value={selectedCaptionClipId} onChange={e => setSelectedCaptionClipId(e.target.value)}
                      className="w-full rounded-lg border border-slate-200 bg-slate-100 px-3 py-2 text-xs text-slate-900 outline-none focus:border-[#1a73e8]">
                      <option value="">Map to whole project</option>
                      {clips.map(clip => {
                        const id = clip.id || clip._id || ""
                        return <option key={id} value={id}>{clip.label || `Clip ${formatTime(clip.start_time || 0)} – ${formatTime(clip.end_time || 0)}`}</option>
                      })}
                    </select>
                    <textarea value={captionText} onChange={e => setCaptionText(e.target.value)} rows={3}
                      placeholder="Paste or type captions here..."
                      className="w-full rounded-lg border border-slate-200 bg-slate-100 px-3 py-2 text-xs text-slate-900 outline-none focus:border-[#1a73e8] resize-none"
                      style={{ fontFamily: selectedFont.family }} />
                    <div className="flex gap-2">
                      <label className="cursor-pointer rounded-lg border border-slate-200 bg-slate-100 px-2 py-1.5 text-[11px] text-slate-600 hover:bg-slate-200 transition-colors">
                        Upload .srt / .txt
                        <input type="file" accept=".txt,.srt,.vtt" onChange={async e => { const f = e.target.files?.[0]; if (f) setCaptionText(await f.text()); e.target.value = "" }} className="hidden" />
                      </label>
                      <button type="submit" disabled={isSavingCaption || !captionText.trim()}
                        className="flex-1 rounded-lg bg-[#1a73e8] py-1.5 text-[11px] font-semibold text-white disabled:opacity-50 hover:bg-[#1557b0] transition-colors">
                        {isSavingCaption ? "Saving…" : "Save Caption"}
                      </button>
                    </div>
                  </form>

                  <div>
                    <p className="text-[10px] font-semibold uppercase text-slate-600 mb-2">Saved ({captions.length})</p>
                    {captions.length === 0 ? (
                      <p className="text-[11px] text-slate-600">No captions yet.</p>
                    ) : captions.map(cap => {
                      const cId = cap.id || cap._id || ""
                      const isEditing = editingCaptionId === cId
                      return (
                        <div key={cId} className="mb-2 rounded-lg border border-slate-200 bg-white p-2.5">
                          {isEditing ? (
                            <div className="space-y-1.5">
                              <textarea value={editingText} onChange={e => setEditingText(e.target.value)} rows={2}
                                className="w-full rounded border border-slate-200 bg-slate-100 px-2 py-1 text-[11px] text-slate-900 outline-none focus:border-[#1a73e8]"
                                style={{ fontFamily: selectedFont.family }} />
                              <div className="flex gap-1.5">
                                <button onClick={() => handleUpdateCaption(cId)} className="rounded bg-[#1a73e8] px-2 py-0.5 text-[10px] font-semibold text-white">Save</button>
                                <button onClick={() => setEditingCaptionId(null)} className="rounded border border-slate-200 px-2 py-0.5 text-[10px] text-slate-600">Cancel</button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <p className="line-clamp-2 text-[11px] text-slate-600" style={{ fontFamily: selectedFont.family }}>{cap.raw_text}</p>
                              <div className="mt-1.5 flex justify-between text-[10px] text-slate-600">
                                <span>Clip: {cap.clip_id ? cap.clip_id.slice(-6) : "project"}</span>
                                <div className="flex gap-2">
                                  <button onClick={() => { setEditingCaptionId(cId); setEditingText(cap.raw_text || "") }} className="text-[#1a73e8] hover:underline">Edit</button>
                                  <button onClick={() => handleDeleteCaption(cId)} className="text-red-400 hover:underline">Del</button>
                                </div>
                              </div>
                            </>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* ── B-ROLL ── */}
              {sidePanel === "broll" && (
                <div className="space-y-3">
                  <div className="flex rounded-lg border border-slate-200 overflow-hidden">
                    <button onClick={() => setShowGallery(false)} className={`flex-1 py-1.5 text-[11px] font-semibold ${!showGallery ? "bg-[#1a73e8] text-white" : "text-slate-600 hover:bg-slate-100"}`}>Search</button>
                    <button onClick={() => { setShowGallery(true); loadSavedAssets() }} className={`flex-1 py-1.5 text-[11px] font-semibold ${showGallery ? "bg-[#1a73e8] text-white" : "text-slate-600 hover:bg-slate-100"}`}>Gallery ({savedAssets.length})</button>
                  </div>

                  {saveMessage && <p className="text-[11px] text-emerald-400">{saveMessage}</p>}

                  {!showGallery ? (
                    <>
                      <form onSubmit={handleSearchAssets} className="space-y-2">
                        <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search stock images..."
                          className="w-full rounded-lg border border-slate-200 bg-slate-100 px-3 py-2 text-xs text-slate-900 outline-none focus:border-[#1a73e8]" />
                        <div className="flex gap-2">
                          <select value={searchSource} onChange={e => setSearchSource(e.target.value as "all" | "pexels" | "pixabay")}
                            className="rounded-lg border border-slate-200 bg-slate-100 px-2 py-1.5 text-[11px] text-slate-900">
                            <option value="all">All</option>
                            <option value="pexels">Pexels</option>
                            <option value="pixabay">Pixabay</option>
                          </select>
                          <button type="submit" disabled={isSearching} className="flex-1 rounded-lg bg-slate-100 border border-slate-200 py-1.5 text-[11px] font-semibold text-slate-900 disabled:opacity-50 hover:bg-slate-200">
                            {isSearching ? "Searching…" : "Search"}
                          </button>
                        </div>
                      </form>
                      <div className="grid grid-cols-2 gap-1.5">
                        {searchResults.length === 0 ? (
                          <p className="col-span-2 text-[11px] text-slate-600">Search for images to use as B-roll.</p>
                        ) : searchResults.map(asset => (
                          <div key={`${asset.source}-${asset.source_id}`} className="overflow-hidden rounded-lg border border-slate-200">
                            <div className="aspect-video bg-slate-100">
                              {asset.thumbnail_url
                                ? <img src={asset.thumbnail_url} alt="Asset" className="h-full w-full object-cover" />
                                : <div className="flex h-full items-center justify-center text-[10px] text-slate-600">No preview</div>}
                            </div>
                            <div className="p-1.5">
                              <button onClick={() => handleSaveAsset(asset)} disabled={savingAssetId === asset.source_id}
                                className="w-full rounded border border-slate-200 py-1 text-[10px] text-slate-600 hover:bg-slate-100 disabled:opacity-50">
                                {savingAssetId === asset.source_id ? "Saving…" : "Save"}
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    /* ── GALLERY with delete/select RESTORED ── */
                    <div>
                      <div className="mb-3 flex items-center justify-between">
                        <p className="text-[10px] font-semibold uppercase text-slate-600">
                          Gallery
                          {isSelectMode && savedAssets.length > 0 && <span className="ml-1 text-[#777]">({selectedAssetIds.size} selected)</span>}
                        </p>
                        <div className="flex gap-1.5">
                          {isSelectMode && savedAssets.length > 0 && (
                            <button onClick={handleSelectAll}
                              className="rounded border border-[#1a73e8]/30 px-2 py-0.5 text-[10px] font-medium text-[#1a73e8] hover:bg-[#1a73e8]/10">
                              {allSelected ? "Deselect All" : "Select All"}
                            </button>
                          )}
                          <button onClick={() => { setIsSelectMode(p => !p); setSelectedAssetIds(new Set()) }}
                            className="rounded border border-slate-200 px-2 py-0.5 text-[10px] font-medium text-slate-600 hover:bg-slate-100">
                            {isSelectMode ? "Cancel" : "Select"}
                          </button>
                          {isSelectMode && selectedAssetIds.size > 0 && (
                            <button onClick={handleDeleteSelectedAssets} disabled={isDeletingSelected}
                              className="flex items-center gap-1 rounded border border-red-500/30 bg-red-500/10 px-2 py-0.5 text-[10px] font-medium text-red-400 hover:bg-red-500/20 disabled:opacity-50">
                              <TrashIcon className="w-3 h-3" />
                              {isDeletingSelected ? "…" : `Delete (${selectedAssetIds.size})`}
                            </button>
                          )}
                        </div>
                      </div>

                      {savedAssets.length === 0 ? (
                        <p className="text-[11px] text-slate-600">No saved images yet.</p>
                      ) : (
                        <div className="grid grid-cols-2 gap-1.5">
                          {savedAssets.map(asset => {
                            const assetId = asset.id || asset._id || ""
                            const key = assetId || asset.url
                            const preview = asset.thumbnail_url || asset.url
                            const selected = selectedAssetIds.has(assetId)
                            const isDeleting = deletingAssetId === assetId
                            return (
                              <div key={key}
                                className={`group relative overflow-hidden rounded-lg border transition-all ${selected ? "border-[#1a73e8] ring-1 ring-[#1a73e8]/40" : "border-slate-200"}`}>
                                <button
                                  onClick={() => {
                                    if (isSelectMode && assetId) { toggleAssetSelection(assetId); return }
                                    if (asset.url) window.open(asset.url, "_blank", "noopener,noreferrer")
                                  }}
                                  className="w-full">
                                  <div className="aspect-square bg-slate-100">
                                    {preview
                                      ? <img src={preview} alt="Saved" className="h-full w-full object-cover" />
                                      : <div className="flex h-full items-center justify-center text-[10px] text-slate-600">No preview</div>}
                                  </div>
                                </button>

                                {/* Select checkbox */}
                                {isSelectMode && (
                                  <div className="absolute right-1 top-1">
                                    <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold shadow ${selected ? "bg-[#1a73e8] text-white" : "bg-slate-700/10 text-slate-900 border border-slate-300"}`}>
                                      {selected ? "✓" : ""}
                                    </span>
                                  </div>
                                )}

                                {/* ── Delete button on hover (RESTORED) ── */}
                                {!isSelectMode && assetId && (
                                  <button
                                    onClick={(e) => handleDeleteSingleAsset(assetId, e)}
                                    disabled={isDeleting}
                                    className="absolute right-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-black/70 text-red-400 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500/20 disabled:opacity-50"
                                    title="Delete image">
                                    {isDeleting
                                      ? <span className="h-3 w-3 animate-spin rounded-full border border-red-400 border-t-transparent" />
                                      : <TrashIcon className="w-3 h-3" />}
                                  </button>
                                )}
                              </div>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* ── TEMPLATES ── */}
              {sidePanel === "templates" && (
                <div className="space-y-2">
                  <p className="text-[11px] text-slate-600">Apply clip style, caption style, and B-roll pattern automatically.</p>
                  {TEMPLATES.map(tmpl => (
                    <button key={tmpl.key} onClick={() => setSelectedTemplate(selectedTemplate === tmpl.key ? null : tmpl.key)}
                      className={`w-full rounded-xl border p-3 text-left transition-all ${selectedTemplate === tmpl.key ? "border-[#1a73e8] bg-[#1a73e8]/10" : "border-slate-200 bg-slate-50 hover:border-slate-300"}`}>
                      <div className="flex items-center gap-2">
                        <span className="text-xl">{tmpl.icon}</span>
                        <div>
                          <p className="text-xs font-semibold text-white">{tmpl.label}</p>
                          <p className="text-[10px] text-slate-600">{tmpl.description}</p>
                        </div>
                        {selectedTemplate === tmpl.key && <span className="ml-auto rounded-full bg-[#1a73e8] px-2 py-0.5 text-[9px] font-bold text-white">Selected</span>}
                      </div>
                    </button>
                  ))}
                  {selectedTemplate && (
                    <div className="rounded-lg border border-amber-800/50 bg-amber-900/20 px-3 py-2 text-[11px] text-amber-400">
                      Template auto-apply coming soon.
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}