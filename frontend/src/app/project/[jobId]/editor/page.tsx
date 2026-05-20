"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import { useParams, useRouter } from "next/navigation"
import api from "@/lib/api"

// ── Types ──────────────────────────────────────────────────────────────────
type ProjectData = {
  id?: string; _id?: string; title?: string; status?: string
  cloudinary_raw_url?: string | null; local_video_path?: string | null
  video_url?: string | null; thumbnail_url?: string | null
  duration_seconds?: number | null; yt_url?: string; yt_video_id?: string
  created_at?: string; metadata?: Record<string, unknown> | null
}
type ClipData = {
  id?: string; _id?: string; label?: string | null
  start_time?: number; end_time?: number; duration?: number
  status?: string; cloudinary_clip_url?: string | null; thumbnail_url?: string | null
}
type CaptionItem = {
  id?: string; _id?: string; clip_id?: string | null
  raw_text?: string; created_at?: string; updated_at?: string
}
type SavedAsset = {
  id?: string; _id?: string; source?: "pexels" | "pixabay"
  asset_type?: "image" | "video"; url?: string
  thumbnail_url?: string | null; photographer?: string | null
}
type AssetResult = {
  source_id: string; source: "pexels" | "pixabay"; asset_type: "image" | "video"
  url: string; thumbnail_url?: string | null; photographer?: string | null
}
type SidePanel = "captions" | "broll" | "templates"
type FontEntry = { label: string; family: string }
type VideoLoadState = "idle" | "cloudinary" | "fetching" | "ready" | "error"
type CaptionMode = "global" | "per_clip"

// ── 166 FONTS ────────────────────────────────────────────────────────────
const FONT_CATEGORIES: { label: string; fonts: FontEntry[] }[] = [
  {
    label: "🔥 Bold & Impact",
    fonts: [
      { label: "Bebas Neue",       family: "'Bebas Neue', cursive" },
      { label: "Anton",            family: "'Anton', sans-serif" },
      { label: "Archivo Black",    family: "'Archivo Black', sans-serif" },
      { label: "Alfa Slab One",    family: "'Alfa Slab One', cursive" },
      { label: "Bangers",          family: "'Bangers', cursive" },
      { label: "Oswald",           family: "'Oswald', sans-serif" },
      { label: "Russo One",        family: "'Russo One', sans-serif" },
      { label: "Righteous",        family: "'Righteous', cursive" },
      { label: "Viga",             family: "'Viga', sans-serif" },
      { label: "Fjalla One",       family: "'Fjalla One', sans-serif" },
      { label: "Black Han Sans",   family: "'Black Han Sans', sans-serif" },
      { label: "Boogaloo",         family: "'Boogaloo', cursive" },
      { label: "Bree Serif",       family: "'Bree Serif', serif" },
      { label: "Cantora One",      family: "'Cantora One', sans-serif" },
      { label: "Carter One",       family: "'Carter One', cursive" },
      { label: "Changa One",       family: "'Changa One', italic" },
      { label: "Contrail One",     family: "'Contrail One', cursive" },
      { label: "Eczar",            family: "'Eczar', serif" },
      { label: "Fugaz One",        family: "'Fugaz One', cursive" },
      { label: "Graduate",         family: "'Graduate', cursive" },
      { label: "Gravitas One",     family: "'Gravitas One', cursive" },
      { label: "Headland One",     family: "'Headland One', serif" },
      { label: "Lilita One",       family: "'Lilita One', cursive" },
      { label: "Limelight",        family: "'Limelight', cursive" },
      { label: "Lobster Two",      family: "'Lobster Two', cursive" },
      { label: "Londrina Solid",   family: "'Londrina Solid', cursive" },
      { label: "Patua One",        family: "'Patua One', cursive" },
      { label: "Plaster",          family: "'Plaster', cursive" },
      { label: "Shrikhand",        family: "'Shrikhand', cursive" },
      { label: "Squada One",       family: "'Squada One', cursive" },
    ],
  },
  {
    label: "✨ Clean & Modern",
    fonts: [
      { label: "Poppins",          family: "'Poppins', sans-serif" },
      { label: "Montserrat",       family: "'Montserrat', sans-serif" },
      { label: "Nunito",           family: "'Nunito', sans-serif" },
      { label: "DM Sans",          family: "'DM Sans', sans-serif" },
      { label: "Outfit",           family: "'Outfit', sans-serif" },
      { label: "Raleway",          family: "'Raleway', sans-serif" },
      { label: "Work Sans",        family: "'Work Sans', sans-serif" },
      { label: "Quicksand",        family: "'Quicksand', sans-serif" },
      { label: "Comfortaa",        family: "'Comfortaa', cursive" },
      { label: "Fredoka",          family: "'Fredoka', sans-serif" },
      { label: "Inter",            family: "'Inter', sans-serif" },
      { label: "Jost",             family: "'Jost', sans-serif" },
      { label: "Karla",            family: "'Karla', sans-serif" },
      { label: "Manrope",          family: "'Manrope', sans-serif" },
      { label: "Mulish",           family: "'Mulish', sans-serif" },
      { label: "Noto Sans",        family: "'Noto Sans', sans-serif" },
      { label: "Open Sans",        family: "'Open Sans', sans-serif" },
      { label: "Plus Jakarta Sans",family: "'Plus Jakarta Sans', sans-serif" },
      { label: "Readex Pro",       family: "'Readex Pro', sans-serif" },
      { label: "Rubik",            family: "'Rubik', sans-serif" },
      { label: "Sora",             family: "'Sora', sans-serif" },
      { label: "Ubuntu",           family: "'Ubuntu', sans-serif" },
      { label: "Urbanist",         family: "'Urbanist', sans-serif" },
      { label: "Varela Round",     family: "'Varela Round', sans-serif" },
      { label: "Ysabeau",          family: "'Ysabeau', sans-serif" },
    ],
  },
  {
    label: "🚀 Techy & Futuristic",
    fonts: [
      { label: "Orbitron",         family: "'Orbitron', sans-serif" },
      { label: "Rajdhani",         family: "'Rajdhani', sans-serif" },
      { label: "Audiowide",        family: "'Audiowide', cursive" },
      { label: "Chakra Petch",     family: "'Chakra Petch', sans-serif" },
      { label: "Exo 2",            family: "'Exo 2', sans-serif" },
      { label: "Teko",             family: "'Teko', sans-serif" },
      { label: "Titillium Web",    family: "'Titillium Web', sans-serif" },
      { label: "Barlow Condensed", family: "'Barlow Condensed', sans-serif" },
      { label: "Aldrich",          family: "'Aldrich', sans-serif" },
      { label: "Bai Jamjuree",     family: "'Bai Jamjuree', sans-serif" },
      { label: "Chivo",            family: "'Chivo', sans-serif" },
      { label: "Chivo Mono",       family: "'Chivo Mono', monospace" },
      { label: "Cuprum",           family: "'Cuprum', sans-serif" },
      { label: "Days One",         family: "'Days One', sans-serif" },
      { label: "Exo",              family: "'Exo', sans-serif" },
      { label: "Gemunu Libre",     family: "'Gemunu Libre', sans-serif" },
      { label: "Gugi",             family: "'Gugi', cursive" },
      { label: "Iceland",          family: "'Iceland', cursive" },
      { label: "Jura",             family: "'Jura', sans-serif" },
      { label: "Michroma",         family: "'Michroma', sans-serif" },
      { label: "Nova Square",      family: "'Nova Square', cursive" },
      { label: "Oxanium",          family: "'Oxanium', cursive" },
      { label: "Quantico",         family: "'Quantico', sans-serif" },
      { label: "Share Tech",       family: "'Share Tech', sans-serif" },
      { label: "Syncopate",        family: "'Syncopate', sans-serif" },
      { label: "Unica One",        family: "'Unica One', cursive" },
      { label: "Wallpoet",         family: "'Wallpoet', cursive" },
      { label: "Xanh Mono",        family: "'Xanh Mono', monospace" },
      { label: "Zilla Slab",       family: "'Zilla Slab', serif" },
    ],
  },
  {
    label: "✍️ Handwritten & Fun",
    fonts: [
      { label: "Pacifico",         family: "'Pacifico', cursive" },
      { label: "Caveat",           family: "'Caveat', cursive" },
      { label: "Dancing Script",   family: "'Dancing Script', cursive" },
      { label: "Permanent Marker", family: "'Permanent Marker', cursive" },
      { label: "Indie Flower",     family: "'Indie Flower', cursive" },
      { label: "Lobster",          family: "'Lobster', cursive" },
      { label: "Chewy",            family: "'Chewy', cursive" },
      { label: "Amatic SC",        family: "'Amatic SC', cursive" },
      { label: "Architects Daughter", family: "'Architects Daughter', cursive" },
      { label: "Bad Script",       family: "'Bad Script', cursive" },
      { label: "Barrio",           family: "'Barrio', cursive" },
      { label: "Birthstone",       family: "'Birthstone', cursive" },
      { label: "Courgette",        family: "'Courgette', cursive" },
      { label: "Crafty Girls",     family: "'Crafty Girls', cursive" },
      { label: "Covered By Your Grace", family: "'Covered By Your Grace', cursive" },
      { label: "Delius",           family: "'Delius', cursive" },
      { label: "Fondamento",       family: "'Fondamento', cursive" },
      { label: "Gochi Hand",       family: "'Gochi Hand', cursive" },
      { label: "Grand Hotel",      family: "'Grand Hotel', cursive" },
      { label: "Handlee",          family: "'Handlee', cursive" },
      { label: "Just Another Hand",family: "'Just Another Hand', cursive" },
      { label: "Kaushan Script",   family: "'Kaushan Script', cursive" },
      { label: "Kristi",           family: "'Kristi', cursive" },
      { label: "La Belle Aurore",  family: "'La Belle Aurore', cursive" },
      { label: "Licorice",         family: "'Licorice', cursive" },
      { label: "Long Cang",        family: "'Long Cang', cursive" },
      { label: "Loved by the King",family: "'Loved by the King', cursive" },
      { label: "Marck Script",     family: "'Marck Script', cursive" },
      { label: "Meddon",           family: "'Meddon', cursive" },
      { label: "Meow Script",      family: "'Meow Script', cursive" },
      { label: "Merienda",         family: "'Merienda', cursive" },
      { label: "Mountains of Christmas", family: "'Mountains of Christmas', cursive" },
      { label: "Nerko One",        family: "'Nerko One', cursive" },
      { label: "Nothing You Could Do", family: "'Nothing You Could Do', cursive" },
      { label: "Pangolin",         family: "'Pangolin', cursive" },
      { label: "Patrick Hand",     family: "'Patrick Hand', cursive" },
      { label: "Petemoss",         family: "'Petemoss', cursive" },
      { label: "Pinyon Script",    family: "'Pinyon Script', cursive" },
      { label: "Rock Salt",        family: "'Rock Salt', cursive" },
      { label: "Sacramento",       family: "'Sacramento', cursive" },
      { label: "Satisfy",          family: "'Satisfy', cursive" },
      { label: "Shadows Into Light",family: "'Shadows Into Light', cursive" },
      { label: "Waiting for the Sunrise", family: "'Waiting for the Sunrise', cursive" },
      { label: "Walter Turncoat",  family: "'Walter Turncoat', cursive" },
    ],
  },
  {
    label: "📖 Elegant & Serif",
    fonts: [
      { label: "Playfair Display", family: "'Playfair Display', serif" },
      { label: "Lora",             family: "'Lora', serif" },
      { label: "Merriweather",     family: "'Merriweather', serif" },
      { label: "Cormorant Garamond", family: "'Cormorant Garamond', serif" },
      { label: "Cinzel",           family: "'Cinzel', serif" },
      { label: "Libre Baskerville",family: "'Libre Baskerville', serif" },
      { label: "Arvo",             family: "'Arvo', serif" },
      { label: "Abril Fatface",    family: "'Abril Fatface', cursive" },
      { label: "Alike",            family: "'Alike', serif" },
      { label: "Amethysta",        family: "'Amethysta', serif" },
      { label: "Amiri",            family: "'Amiri', serif" },
      { label: "Antic Slab",       family: "'Antic Slab', serif" },
      { label: "Belleza",          family: "'Belleza', sans-serif" },
      { label: "Bodoni Moda",      family: "'Bodoni Moda', serif" },
      { label: "Bookman Old Style",family: "'Bookman Old Style', serif" },
      { label: "Castoro",          family: "'Castoro', serif" },
      { label: "Caudex",           family: "'Caudex', serif" },
      { label: "Crete Round",      family: "'Crete Round', serif" },
      { label: "Crimson Pro",      family: "'Crimson Pro', serif" },
      { label: "DM Serif Display", family: "'DM Serif Display', serif" },
      { label: "Della Respira",    family: "'Della Respira', serif" },
      { label: "Domine",           family: "'Domine', serif" },
      { label: "Dongle",           family: "'Dongle', sans-serif" },
      { label: "EB Garamond",      family: "'EB Garamond', serif" },
      { label: "Faustina",         family: "'Faustina', serif" },
      { label: "Frank Ruhl Libre", family: "'Frank Ruhl Libre', serif" },
      { label: "Fraunces",         family: "'Fraunces', serif" },
      { label: "GFS Didot",        family: "'GFS Didot', serif" },
      { label: "Gilda Display",    family: "'Gilda Display', serif" },
      { label: "Halant",           family: "'Halant', serif" },
      { label: "Hahmlet",          family: "'Hahmlet', serif" },
      { label: "Italiana",         family: "'Italiana', serif" },
      { label: "Josefin Slab",     family: "'Josefin Slab', serif" },
      { label: "Judson",           family: "'Judson', serif" },
    ],
  },
  {
    label: "💻 Monospace",
    fonts: [
      { label: "Roboto Mono",      family: "'Roboto Mono', monospace" },
      { label: "IBM Plex Mono",    family: "'IBM Plex Mono', monospace" },
      { label: "Space Mono",       family: "'Space Mono', monospace" },
      { label: "Inconsolata",      family: "'Inconsolata', monospace" },
      { label: "Courier Prime",    family: "'Courier Prime', monospace" },
      { label: "Cutive Mono",      family: "'Cutive Mono', monospace" },
      { label: "Fira Code",        family: "'Fira Code', monospace" },
      { label: "Fragment Mono",    family: "'Fragment Mono', monospace" },
      { label: "JetBrains Mono",   family: "'JetBrains Mono', monospace" },
      { label: "Nanum Gothic Coding", family: "'Nanum Gothic Coding', monospace" },
      { label: "Overpass Mono",    family: "'Overpass Mono', monospace" },
      { label: "PT Mono",          family: "'PT Mono', monospace" },
      { label: "Share Tech Mono",  family: "'Share Tech Mono', monospace" },
      { label: "Source Code Pro",  family: "'Source Code Pro', monospace" },
      { label: "Ubuntu Mono",      family: "'Ubuntu Mono', monospace" },
    ],
  },
]
const ALL_FONTS: FontEntry[] = FONT_CATEGORIES.flatMap(c => c.fonts)

// ── Caption colour palette ────────────────────────────────────────────────
const CAPTION_PRESETS: { label: string; text: string; bg: string; bgOpacity: number }[] = [
  { label: "Classic White",  text: "#ffffff", bg: "#000000", bgOpacity: 0.75 },
  { label: "Golden Yellow",  text: "#fbbf24", bg: "#000000", bgOpacity: 0.75 },
  { label: "Neon Cyan",      text: "#22d3ee", bg: "#000000", bgOpacity: 0.75 },
  { label: "Neon Green",     text: "#4ade80", bg: "#000000", bgOpacity: 0.75 },
  { label: "Hot Pink",       text: "#f472b6", bg: "#000000", bgOpacity: 0.75 },
  { label: "Coral Red",      text: "#f87171", bg: "#000000", bgOpacity: 0.75 },
  { label: "Black on White", text: "#111827", bg: "#ffffff", bgOpacity: 0.92 },
  { label: "White on Blue",  text: "#ffffff", bg: "#1d4ed8", bgOpacity: 0.85 },
  { label: "Dark on Yellow", text: "#1a1a1a", bg: "#fbbf24", bgOpacity: 0.95 },
  { label: "White on Red",   text: "#ffffff", bg: "#dc2626", bgOpacity: 0.85 },
  { label: "Mint on Dark",   text: "#6ee7b7", bg: "#064e3b", bgOpacity: 0.85 },
  { label: "Lavender",       text: "#e9d5ff", bg: "#4c1d95", bgOpacity: 0.85 },
]
const TEXT_SWATCHES = [
  "#ffffff","#fbbf24","#22d3ee","#4ade80","#f472b6","#f87171",
  "#111827","#60a5fa","#a78bfa","#34d399","#fb923c","#fcd34d",
  "#e9d5ff","#fed7aa","#f9a8d4","#6ee7b7",
]
const BG_SWATCHES = [
  "#000000","#111827","#1a1a2e","#1d4ed8","#dc2626","#064e3b",
  "#4c1d95","#7c2d12","#1f2937","#ffffff","#fbbf24","#fef3c7",
  "#0f172a","#14532d","#1e1b4b","#450a0a",
]

const TEMPLATES = [
  { key: "podcast",   label: "Podcast",   description: "Speaker focused, lower-third captions", icon: "🎙️" },
  { key: "interview", label: "Interview", description: "Two-speaker, dynamic captions",          icon: "🎤" },
  { key: "tutorial",  label: "Tutorial",  description: "Screen + face pip, step highlights",     icon: "📚" },
  { key: "vlog",      label: "Vlog",      description: "Fast pacing, energetic caption style",   icon: "🎬" },
]

function fmtTime(s: number) {
  if (!s || s < 0) return "0:00"
  const m = Math.floor(s / 60), sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, "0")}`
}

function TrashIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  )
}

// ── Colour Picker Dropdown ─────────────────────────────────────────────────
function ColorPickerDropdown({
  textColor, bgColor, bgOpacity,
  onTextColor, onBgColor, onBgOpacity,
}: {
  textColor: string; bgColor: string; bgOpacity: number
  onTextColor: (c: string) => void; onBgColor: (c: string) => void; onBgOpacity: (n: number) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener("mousedown", h)
    return () => document.removeEventListener("mousedown", h)
  }, [])
  const bgWithOpacity = bgColor + Math.round(bgOpacity * 255).toString(16).padStart(2, "0")

  return (
    <div ref={ref} className="relative">
      {/* Trigger button */}
      <button
        onClick={() => setOpen(p => !p)}
        className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-xs hover:border-slate-300 bg-white transition-colors"
      >
        <div className="flex items-center gap-2">
          {/* Mini preview swatch */}
          <div className="w-14 h-5 rounded text-[9px] font-bold flex items-center justify-center border border-slate-200"
            style={{ backgroundColor: bgWithOpacity, color: textColor }}>
            Abc
          </div>
          <span className="text-slate-500 text-[11px]">Change colors…</span>
        </div>
        <svg className={`w-3.5 h-3.5 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 rounded-xl border border-slate-200 bg-white shadow-2xl overflow-hidden">
          {/* Style Presets */}
          <div className="p-3 border-b border-slate-100">
            <p className="text-[10px] font-semibold uppercase text-slate-400 mb-2">Style Presets</p>
            <div className="grid grid-cols-4 gap-1.5">
              {CAPTION_PRESETS.map(p => (
                <button key={p.label}
                  onClick={() => { onTextColor(p.text); onBgColor(p.bg); onBgOpacity(p.bgOpacity) }}
                  title={p.label}
                  className={`rounded-lg h-9 flex items-center justify-center text-[10px] font-bold border-2 transition-all hover:scale-105
                    ${textColor === p.text && bgColor === p.bg ? "border-[#1a73e8] scale-105 shadow" : "border-transparent hover:border-slate-300"}`}
                  style={{ backgroundColor: p.bg + Math.round(p.bgOpacity * 255).toString(16).padStart(2, "0"), color: p.text }}>
                  Abc
                </button>
              ))}
            </div>
          </div>

          {/* Text colour */}
          <div className="p-3 border-b border-slate-100">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] font-semibold uppercase text-slate-400">Text Color</p>
              <div className="flex items-center gap-1.5">
                <span className="w-4 h-4 rounded border border-slate-300" style={{ backgroundColor: textColor }} />
                <span className="text-[10px] text-slate-500 font-mono">{textColor}</span>
              </div>
            </div>
            <div className="grid grid-cols-8 gap-1">
              {TEXT_SWATCHES.map(c => (
                <button key={c} onClick={() => onTextColor(c)} title={c}
                  className={`w-full aspect-square rounded border-2 transition-all hover:scale-110
                    ${textColor === c ? "border-[#1a73e8] scale-110 shadow" : "border-transparent hover:border-slate-400"}`}
                  style={{ backgroundColor: c, outline: c === "#ffffff" ? "1px solid #e2e8f0" : undefined }} />
              ))}
            </div>
            <label className="flex items-center gap-2 mt-2 cursor-pointer">
              <input type="color" value={textColor} onChange={e => onTextColor(e.target.value)}
                className="w-6 h-6 rounded cursor-pointer border-0 p-0" />
              <span className="text-[10px] text-slate-400">Custom color…</span>
            </label>
          </div>

          {/* BG colour */}
          <div className="p-3 border-b border-slate-100">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] font-semibold uppercase text-slate-400">Background Color</p>
              <div className="flex items-center gap-1.5">
                <span className="w-4 h-4 rounded border border-slate-300" style={{ backgroundColor: bgColor }} />
                <span className="text-[10px] text-slate-500 font-mono">{bgColor}</span>
              </div>
            </div>
            <div className="grid grid-cols-8 gap-1">
              {BG_SWATCHES.map(c => (
                <button key={c} onClick={() => onBgColor(c)} title={c}
                  className={`w-full aspect-square rounded border-2 transition-all hover:scale-110
                    ${bgColor === c ? "border-[#1a73e8] scale-110 shadow" : "border-transparent hover:border-slate-400"}`}
                  style={{ backgroundColor: c, outline: c === "#ffffff" ? "1px solid #e2e8f0" : undefined }} />
              ))}
            </div>
            <label className="flex items-center gap-2 mt-2 cursor-pointer">
              <input type="color" value={bgColor} onChange={e => onBgColor(e.target.value)}
                className="w-6 h-6 rounded cursor-pointer border-0 p-0" />
              <span className="text-[10px] text-slate-400">Custom color…</span>
            </label>
          </div>

          {/* Opacity */}
          <div className="p-3">
            <div className="flex items-center justify-between mb-1.5">
              <p className="text-[10px] font-semibold uppercase text-slate-400">BG Opacity</p>
              <span className="text-[10px] font-semibold text-slate-600">{Math.round(bgOpacity * 100)}%</span>
            </div>
            <input type="range" min={0} max={1} step={0.05} value={bgOpacity}
              onChange={e => onBgOpacity(Number(e.target.value))}
              className="w-full h-1.5 rounded-full appearance-none bg-slate-200 accent-[#1a73e8]" />
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main Component ─────────────────────────────────────────────────────────
export default function VideoEditor() {
  const params    = useParams()
  const router    = useRouter()
  const projectId = params.jobId as string

  const videoRef      = useRef<HTMLVideoElement>(null)
  const timelineRef   = useRef<HTMLDivElement>(null)
  const fontPickerRef = useRef<HTMLDivElement>(null)
  const blobUrlRef    = useRef<string | null>(null)

  const [project, setProject]   = useState<ProjectData | null>(null)
  const [clips,   setClips]     = useState<ClipData[]>([])
  const [loading, setLoading]   = useState(true)
  const [error,   setError]     = useState<string | null>(null)

  const [duration,       setDuration]       = useState(0)
  const [currentTime,    setCurrentTime]    = useState(0)
  const [isPlaying,      setIsPlaying]      = useState(false)
  const [videoLoadState, setVideoLoadState] = useState<VideoLoadState>("idle")
  const [videoBlobUrl,   setVideoBlobUrl]   = useState<string | null>(null)
  const [videoErrorMsg,  setVideoErrorMsg]  = useState<string | null>(null)

  const [clipDuration, setClipDuration] = useState<30 | 60 | null>(null)
  const [selStart,     setSelStart]     = useState(0)
  const [splitPoints,  setSplitPoints]  = useState<number[]>([])

  const isDraggingSelRef      = useRef(false)
  const isDraggingPlayheadRef = useRef(false)
  const dragStartXRef         = useRef(0)
  const dragStartSelRef       = useRef(0)
  const [, forceUpdate]       = useState(0)

  const [isCreatingClip, setIsCreatingClip] = useState(false)
  const [createSuccess,  setCreateSuccess]  = useState(false)

  const [sidePanel,      setSidePanel]      = useState<SidePanel>("captions")
  const [rightPanelOpen, setRightPanelOpen] = useState(true)

  const [captions,              setCaptions]              = useState<CaptionItem[]>([])
  const [captionText,           setCaptionText]           = useState("")
  const [isSavingCaption,       setIsSavingCaption]       = useState(false)
  const [selectedCaptionClipId, setSelectedCaptionClipId] = useState("")
  const [editingCaptionId,      setEditingCaptionId]      = useState<string | null>(null)
  const [editingText,           setEditingText]           = useState("")
  const [selectedFont,          setSelectedFont]          = useState<FontEntry>(ALL_FONTS[0])
  const [showFontPicker,        setShowFontPicker]        = useState(false)
  const [fontSearch,            setFontSearch]            = useState("")
  const [captionTextColor,      setCaptionTextColor]      = useState("#ffffff")
  const [captionBgColor,        setCaptionBgColor]        = useState("#000000")
  const [captionBgOpacity,      setCaptionBgOpacity]      = useState(0.75)
  const [captionMode,           setCaptionMode]           = useState<CaptionMode>("global")

  const [searchQuery,        setSearchQuery]        = useState("")
  const [searchSource,       setSearchSource]       = useState<"all"|"pexels"|"pixabay">("all")
  const [searchResults,      setSearchResults]      = useState<AssetResult[]>([])
  const [isSearching,        setIsSearching]        = useState(false)
  const [savedAssets,        setSavedAssets]        = useState<SavedAsset[]>([])
  const [savingAssetId,      setSavingAssetId]      = useState<string | null>(null)
  const [showGallery,        setShowGallery]        = useState(false)
  const [saveMessage,        setSaveMessage]        = useState<string | null>(null)
  const [isSelectMode,       setIsSelectMode]       = useState(false)
  const [selectedAssetIds,   setSelectedAssetIds]   = useState<Set<string>>(new Set())
  const [isDeletingSelected, setIsDeletingSelected] = useState(false)
  const [deletingAssetId,    setDeletingAssetId]    = useState<string | null>(null)
  const [selectedTemplate,   setSelectedTemplate]   = useState<string | null>(null)

  const isYT = !!(project && !project.cloudinary_raw_url && !project.video_url && project.yt_video_id)

  useEffect(() => () => { if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current) }, [])

  const loadProject = useCallback(async () => {
    try {
      const [pR, cR] = await Promise.all([
        api.get(`/api/v1/projects/${projectId}`),
        api.get(`/api/v1/projects/${projectId}/clips`),
      ])
      const proj: ProjectData = pR.data
      setProject(proj)
      if (proj.duration_seconds && proj.duration_seconds > 0) setDuration(proj.duration_seconds)
      setClips(Array.isArray(cR.data) ? cR.data : [])
    } catch { setError("Could not load project.") }
    finally { setLoading(false) }
  }, [projectId])

  const loadCaptions = useCallback(async () => {
    try { const r = await api.get(`/api/v1/projects/${projectId}/captions`); setCaptions(Array.isArray(r.data) ? r.data : []) }
    catch { /* non-blocking */ }
  }, [projectId])

  const loadSavedAssets = useCallback(async () => {
    try { const r = await api.get(`/api/v1/projects/${projectId}/assets`); setSavedAssets(Array.isArray(r.data) ? r.data : []) }
    catch { /* non-blocking */ }
  }, [projectId])

  useEffect(() => {
    const t = localStorage.getItem("token")
    if (!t) { router.push("/login"); return }
    if (!projectId || projectId === "undefined") { router.push("/dashboard"); return }
    loadProject(); loadCaptions(); loadSavedAssets()
  }, [loadProject, loadCaptions, loadSavedAssets, router, projectId])

  const fetchVideoAsBlob = useCallback(async () => {
    setVideoLoadState("fetching"); setVideoErrorMsg(null)
    try {
      const res = await api.get(`/api/v1/projects/${projectId}/stream`, { responseType: "blob" })
      const url = URL.createObjectURL(new Blob([res.data], { type: "video/mp4" }))
      if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = url; setVideoBlobUrl(url); setVideoLoadState("ready")
    } catch (err: unknown) {
      const s = (err as { response?: { status?: number } })?.response?.status
      if (s === 401 || s === 403) setVideoErrorMsg("Authentication failed.")
      else if (s === 404)         setVideoErrorMsg("Video file not found on server.")
      else                        setVideoErrorMsg("Could not load video. Check backend is running.")
      setVideoLoadState("error")
    }
  }, [projectId])

  useEffect(() => {
    if (!project || videoLoadState !== "idle") return
    const cloudUrl = project.cloudinary_raw_url || project.video_url
    if (cloudUrl) { setVideoLoadState("cloudinary"); setVideoBlobUrl(cloudUrl) }
    else if (project.yt_video_id) {
      const orig = typeof window !== "undefined" ? encodeURIComponent(window.location.origin) : ""
      setVideoBlobUrl(`https://www.youtube-nocookie.com/embed/${project.yt_video_id}?rel=0&modestbranding=1&enablejsapi=1&origin=${orig}`)
      setVideoLoadState("ready")
    } else { fetchVideoAsBlob() }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project])

  useEffect(() => { if (videoLoadState === "cloudinary" && videoBlobUrl) setVideoLoadState("ready") }, [videoLoadState, videoBlobUrl])

  const handleRetryVideo = () => {
    setVideoLoadState("idle"); setVideoBlobUrl(null); setVideoErrorMsg(null)
    if (!project) return
    const cloudUrl = project.cloudinary_raw_url || project.video_url
    if (cloudUrl) { setVideoLoadState("cloudinary"); setVideoBlobUrl(cloudUrl) }
    else if (project.yt_video_id) {
      const orig = typeof window !== "undefined" ? encodeURIComponent(window.location.origin) : ""
      setVideoBlobUrl(`https://www.youtube-nocookie.com/embed/${project.yt_video_id}?rel=0&modestbranding=1&enablejsapi=1&origin=${orig}`)
      setVideoLoadState("ready")
    } else fetchVideoAsBlob()
  }

  const handleLoadedMetadata = () => { if (videoRef.current?.duration && videoRef.current.duration > 0) setDuration(videoRef.current.duration) }
  const handleTimeUpdate     = () => { if (videoRef.current) setCurrentTime(videoRef.current.currentTime) }
  const handleVideoError     = () => {
    if (videoLoadState === "cloudinary") { setVideoBlobUrl(null); setVideoLoadState("idle"); fetchVideoAsBlob() }
    else { setVideoErrorMsg("Video format not supported."); setVideoLoadState("error") }
  }
  const handlePlayPause = () => {
    if (!videoRef.current) return
    if (videoRef.current.paused) { videoRef.current.play(); setIsPlaying(true) }
    else                         { videoRef.current.pause(); setIsPlaying(false) }
  }

  const getTimeFromMouseX = useCallback((clientX: number): number => {
    if (!timelineRef.current || duration === 0) return 0
    const rect = timelineRef.current.getBoundingClientRect()
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)) * duration
  }, [duration])

  const getPxPerSec = useCallback((): number => {
    if (!timelineRef.current || duration === 0) return 0
    return timelineRef.current.getBoundingClientRect().width / duration
  }, [duration])

  const handleTimelineClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (isDraggingSelRef.current || isDraggingPlayheadRef.current) return
    if (duration === 0) return
    const t = getTimeFromMouseX(e.clientX)
    setCurrentTime(t)
    if (videoRef.current) videoRef.current.currentTime = t
  }, [duration, getTimeFromMouseX])

  const handlePlayheadMouseDown = useCallback((e: React.MouseEvent) => {
    e.stopPropagation(); e.preventDefault(); isDraggingPlayheadRef.current = true
  }, [])

  const handleSelBoxMouseDown = useCallback((e: React.MouseEvent) => {
    e.stopPropagation(); e.preventDefault()
    isDraggingSelRef.current = true; dragStartXRef.current = e.clientX; dragStartSelRef.current = selStart
  }, [selStart])

  const handleHandleMouseDown = useCallback((e: React.MouseEvent) => {
    e.stopPropagation(); e.preventDefault()
    isDraggingSelRef.current = true; dragStartXRef.current = e.clientX; dragStartSelRef.current = selStart
  }, [selStart])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const pps = getPxPerSec(); if (pps === 0) return
      if (isDraggingPlayheadRef.current) {
        const t = getTimeFromMouseX(e.clientX); setCurrentTime(t)
        if (videoRef.current) videoRef.current.currentTime = t; forceUpdate(n => n + 1)
      }
      if (isDraggingSelRef.current && clipDuration !== null) {
        const delta = (e.clientX - dragStartXRef.current) / pps
        setSelStart(Math.max(0, Math.min(dragStartSelRef.current + delta, Math.max(0, duration - clipDuration))))
      }
    }
    const onUp = () => { isDraggingSelRef.current = false; isDraggingPlayheadRef.current = false }
    document.addEventListener("mousemove", onMove); document.addEventListener("mouseup", onUp)
    return () => { document.removeEventListener("mousemove", onMove); document.removeEventListener("mouseup", onUp) }
  }, [duration, clipDuration, getPxPerSec, getTimeFromMouseX])

  useEffect(() => {
    const h = (e: MouseEvent) => { if (fontPickerRef.current && !fontPickerRef.current.contains(e.target as Node)) setShowFontPicker(false) }
    document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h)
  }, [])

  const handleSplit = useCallback(() => {
    if (currentTime > 0.5 && currentTime < duration - 0.5)
      setSplitPoints(prev => [...prev.filter(p => Math.abs(p - currentTime) > 1), currentTime].sort((a, b) => a - b))
  }, [currentTime, duration])

  // ── Clip overlap helpers (float-safe: 0.5s tolerance) ──
  const selectionOverlaps = useCallback((start: number, dur: number): boolean => {
    const end = start + dur
    return clips.some(c => start < (c.end_time ?? 0) - 0.5 && end > (c.start_time ?? 0) + 0.5)
  }, [clips])

  const findNextFree = useCallback((dur: number, afterTime: number): number | null => {
    const ok = (t: number) => {
      const end = t + dur
      return end <= duration && !clips.some(c => t < (c.end_time ?? 0) - 0.5 && end > (c.start_time ?? 0) + 0.5)
    }
    for (let t = afterTime; t <= duration - dur; t += 1) if (ok(t)) return t
    for (let t = 0;         t < afterTime;       t += 1) if (ok(t)) return t
    return null
  }, [clips, duration])

  // ── CREATE CLIP ── pre-checks locally, never hits a 409 blind
  const handleCreateClip = async () => {
    if (!clipDuration)  { setError("Select 30s or 60s first."); return }
    if (duration === 0) { setError("Timeline not loaded yet."); return }

    // Local overlap check first
    if (selectionOverlaps(selStart, clipDuration)) {
      const next = findNextFree(clipDuration, selStart + clipDuration)
      if (next !== null) {
        setSelStart(next)
        setError(`That segment is taken. Selection moved to ${fmtTime(next)}–${fmtTime(next + clipDuration)}. Click Create Clip again.`)
      } else {
        setError("No free segment found. Remove some clips or try the other duration.")
      }
      return
    }

    setIsCreatingClip(true); setError(null)
    try {
      await api.post(`/api/v1/projects/${projectId}/clips`, {
        start_time: selStart,
        end_time:   selStart + clipDuration,
        clip_type:  `${clipDuration}s`,
      })
      await loadProject()
      setCreateSuccess(true); setTimeout(() => setCreateSuccess(false), 2500)
      const next = findNextFree(clipDuration, selStart + clipDuration)
      if (next !== null) setSelStart(next)
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 409) {
        await loadProject()
        const next = findNextFree(clipDuration, selStart + clipDuration)
        if (next !== null) { setSelStart(next); setError(`Server rejected. Moved to ${fmtTime(next)}–${fmtTime(next + clipDuration)}. Click again.`) }
        else setError("All segments taken. Remove existing clips to free space.")
      } else { setError("Could not create clip. Please try again.") }
    } finally { setIsCreatingClip(false) }
  }

  const handleClipDurationToggle = (d: 30 | 60) => {
    if (clipDuration === d) { setClipDuration(null); return }
    setClipDuration(d)
    setSelStart(prev => Math.max(0, Math.min(prev, Math.max(0, (duration || 999) - d))))
  }

  const handleSaveCaption = async (e: React.FormEvent) => {
    e.preventDefault(); if (!captionText.trim()) return
    setIsSavingCaption(true)
    try {
      await api.post(`/api/v1/projects/${projectId}/captions`, {
        raw_text: captionText.trim(),
        clip_id:  captionMode === "per_clip" ? (selectedCaptionClipId || null) : null,
        font_family: selectedFont.family, text_color: captionTextColor,
        bg_color: captionBgColor, bg_opacity: captionBgOpacity,
      })
      setCaptionText(""); await loadCaptions()
    } catch { setError("Could not save caption.") }
    finally { setIsSavingCaption(false) }
  }

  const handleUpdateCaption = async (id: string) => {
    if (!editingText.trim()) return
    try { await api.patch(`/api/v1/captions/${id}`, { raw_text: editingText.trim() }); setEditingCaptionId(null); setEditingText(""); await loadCaptions() }
    catch { setError("Could not update caption.") }
  }
  const handleDeleteCaption = async (id: string) => {
    try { await api.delete(`/api/v1/captions/${id}`); await loadCaptions() }
    catch { setError("Could not delete caption.") }
  }

  const handleSearchAssets = async (e: React.FormEvent) => {
    e.preventDefault(); if (!searchQuery.trim()) return; setIsSearching(true)
    try { const r = await api.get("/api/v1/assets/search", { params: { q: searchQuery.trim(), type: "image", source: searchSource, per_page: 18 } }); setSearchResults(Array.isArray(r.data?.results) ? r.data.results : []) }
    catch { setError("Could not search assets.") } finally { setIsSearching(false) }
  }

  const handleSaveAsset = async (asset: AssetResult) => {
    setSavingAssetId(asset.source_id); setSaveMessage(null)
    try {
      const r = await api.post(`/api/v1/projects/${projectId}/assets`, {
        source_id: asset.source_id, source: asset.source, asset_type: asset.asset_type,
        url: asset.url, thumbnail_url: asset.thumbnail_url, query_used: searchQuery.trim(), photographer: asset.photographer,
      })
      setSaveMessage("Saved!"); setSavedAssets(prev => [r.data as SavedAsset, ...prev]); setTimeout(() => setSaveMessage(null), 2000)
    } catch (err: unknown) {
      const s = (err as { response?: { status?: number } })?.response?.status
      if (s === 409) window.alert("Already saved."); else setError("Could not save asset.")
    } finally { setSavingAssetId(null) }
  }

  const toggleAssetSel = (id: string) => setSelectedAssetIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
  const allSelected = savedAssets.length > 0 && selectedAssetIds.size === savedAssets.length
  const handleSelectAll = () => {
    const all = new Set(savedAssets.map(a => a.id || a._id || "").filter(Boolean))
    setSelectedAssetIds(selectedAssetIds.size === all.size ? new Set() : all)
  }
  const handleDeleteSingleAsset = async (assetId: string, e: React.MouseEvent) => {
    e.stopPropagation(); if (!window.confirm("Delete this image?")) return; setDeletingAssetId(assetId)
    try { await api.delete(`/api/v1/assets/${assetId}`); setSavedAssets(prev => prev.filter(a => (a.id || a._id) !== assetId)) }
    catch { setError("Could not delete image.") } finally { setDeletingAssetId(null) }
  }
  const handleDeleteSelectedAssets = async () => {
    if (!selectedAssetIds.size || isDeletingSelected) return
    if (!window.confirm(`Delete ${selectedAssetIds.size} image(s)?`)) return
    setIsDeletingSelected(true)
    try {
      await Promise.all(Array.from(selectedAssetIds).map(id => api.delete(`/api/v1/assets/${id}`)))
      setSavedAssets(prev => prev.filter(a => !selectedAssetIds.has(a.id || a._id || "")))
      setSelectedAssetIds(new Set()); setIsSelectMode(false)
    } catch { setError("Could not delete images.") } finally { setIsDeletingSelected(false) }
  }

  const selPctStart  = duration > 0 && clipDuration !== null ? (selStart / duration) * 100 : 0
  const selPctWidth  = duration > 0 && clipDuration !== null ? (clipDuration / duration) * 100 : 0
  const playheadPct  = duration > 0 ? (currentTime / duration) * 100 : 0
  const tickInterval = duration > 600 ? 60 : duration > 120 ? 30 : 10
  const filteredFonts = fontSearch.trim() ? ALL_FONTS.filter(f => f.label.toLowerCase().includes(fontSearch.toLowerCase())) : null
  const captionBgWithAlpha = captionBgColor + Math.round(captionBgOpacity * 255).toString(16).padStart(2, "0")

  if (loading) return (
    <div className="flex min-h-screen items-center justify-center bg-[#f8fbff]">
      <div className="text-center">
        <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-[#1a73e8] border-t-transparent" />
        <p className="text-sm text-slate-600">Loading editor…</p>
      </div>
    </div>
  )

  return (
    <div className="flex flex-col h-screen bg-[#f8fbff] text-slate-900 overflow-hidden" style={{ fontFamily: "'DM Sans', sans-serif" }}>

      {/* ── HEADER ── */}
      <header className="flex items-center justify-between px-4 h-11 border-b border-slate-200 bg-white flex-shrink-0 z-50">
        <div className="flex items-center gap-3">
          <button onClick={() => router.push("/dashboard")} className="text-xs text-slate-600 hover:text-slate-900 px-2">← Back</button>
          <div className="w-px h-5 bg-slate-200" />
          <span className="text-xs text-slate-600 truncate max-w-[260px]">{project?.title || "Untitled"}</span>
        </div>
        <div className="flex items-center gap-2">
          {error && (
            <div className="flex items-center gap-1 max-w-md">
              <span className="text-xs text-red-500 truncate">{error}</span>
              <button onClick={() => setError(null)} className="text-red-400 text-xs ml-1 flex-shrink-0">✕</button>
            </div>
          )}
          {createSuccess && <span className="text-xs text-emerald-500 font-semibold">✓ Clip created!</span>}
          <button onClick={handleCreateClip} disabled={isCreatingClip || !clipDuration}
            title={!clipDuration ? "Select 30s or 60s first" : `Create ${clipDuration}s clip`}
            className="rounded-lg bg-[#1a73e8] px-4 py-1.5 text-xs font-semibold text-white hover:bg-[#1557b0] disabled:opacity-50 disabled:cursor-not-allowed transition-all">
            {isCreatingClip ? "Creating…" : clipDuration ? `Create Clip (${clipDuration}s)` : "Create Clip"}
          </button>
        </div>
      </header>

      <div className="flex flex-1 min-h-0">

        {/* ── VIDEO + TIMELINE ── */}
        <div className="flex flex-col flex-1 min-w-0">

          {/* Video */}
          <div className="flex-1 flex items-center justify-center bg-slate-900 relative overflow-hidden">
            {(videoLoadState === "idle" || videoLoadState === "fetching") && (
              <div className="flex flex-col items-center gap-3 text-slate-400">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-[#1a73e8] border-t-transparent" />
                <p className="text-sm">{videoLoadState === "fetching" ? "Loading video…" : "Preparing…"}</p>
              </div>
            )}
            {videoLoadState === "error" && (
              <div className="flex flex-col items-center gap-4 px-8 text-center">
                <svg className="w-12 h-12 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <p className="text-sm text-red-400">{videoErrorMsg || "Could not load video."}</p>
                <button onClick={handleRetryVideo} className="rounded-lg bg-[#1a73e8] px-4 py-1.5 text-xs font-semibold text-white hover:bg-[#1557b0]">Retry</button>
              </div>
            )}
            {(videoLoadState === "ready" || videoLoadState === "cloudinary") && videoBlobUrl && (
              isYT ? (
                <iframe key={videoBlobUrl} src={videoBlobUrl} className="rounded-lg shadow-2xl"
                  style={{ width: "100%", maxWidth: 860, aspectRatio: "16/9", border: "none" }}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                  allowFullScreen referrerPolicy="strict-origin-when-cross-origin" title={project?.title || "Video"} />
              ) : (
                <video key={videoBlobUrl} ref={videoRef} src={videoBlobUrl} controls preload="metadata"
                  poster={project?.thumbnail_url || undefined}
                  onLoadedMetadata={handleLoadedMetadata} onTimeUpdate={handleTimeUpdate}
                  onPlay={() => setIsPlaying(true)} onPause={() => setIsPlaying(false)} onError={handleVideoError}
                  className="max-w-full max-h-full rounded-lg shadow-2xl" style={{ maxHeight: "calc(100% - 32px)" }} />
              )
            )}
          </div>

          {/* ── TIMELINE ── */}
          <div className="flex-shrink-0 border-t border-slate-200 bg-white" style={{ userSelect: "none" }}>

            {/* Toolbar */}
            <div className="flex items-center justify-between px-4 h-10 border-b border-slate-200 gap-2">
              {/* Split */}
              <div className="flex items-center gap-1">
                <button onClick={handleSplit}
                  disabled={isYT || duration === 0 || currentTime < 0.5 || currentTime > duration - 0.5}
                  title={isYT ? "Split unavailable for YouTube videos" : "Split at playhead"}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium text-slate-600 hover:text-[#1a73e8] hover:bg-blue-50 disabled:opacity-30 disabled:cursor-not-allowed transition-all border border-transparent hover:border-blue-200">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <circle cx="6" cy="6" r="3" strokeWidth={2}/><circle cx="6" cy="18" r="3" strokeWidth={2}/>
                    <line x1="20" y1="4" x2="8.12" y2="15.88" strokeWidth={2} strokeLinecap="round"/>
                    <line x1="14.47" y1="14.48" x2="20" y2="20" strokeWidth={2} strokeLinecap="round"/>
                    <line x1="8.12" y1="8.12" x2="12" y2="12" strokeWidth={2} strokeLinecap="round"/>
                  </svg>
                  <span className="text-[11px]">Split</span>
                </button>
                {splitPoints.length > 0 && (
                  <button onClick={() => setSplitPoints([])}
                    className="flex items-center gap-1 px-2 py-1 rounded text-[11px] text-red-500 hover:bg-red-50 border border-transparent hover:border-red-200">
                    <TrashIcon className="w-3 h-3" /> Clear splits ({splitPoints.length})
                  </button>
                )}
              </div>

              {/* Playback + time */}
              <div className="flex items-center gap-2">
                <button onClick={() => { setCurrentTime(0); if (videoRef.current) videoRef.current.currentTime = 0 }}
                  title="Go to start" className="text-slate-500 hover:text-slate-900">
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>
                </button>
                <button onClick={handlePlayPause} disabled={isYT}
                  title={isYT ? "Use YouTube player controls" : isPlaying ? "Pause" : "Play"}
                  className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
                  {isPlaying
                    ? <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                    : <svg className="w-4 h-4 ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>}
                </button>
                <button onClick={() => { if (videoRef.current) videoRef.current.currentTime = Math.min(duration, videoRef.current.currentTime + 5) }}
                  disabled={isYT} title="Skip +5s" className="text-slate-500 hover:text-slate-900 disabled:opacity-40 disabled:cursor-not-allowed">
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 18l8.5-6L6 6v12zm2.5-6l5.5 3.9V8.1L8.5 12zM16 6h2v12h-2z"/></svg>
                </button>
                <span className="text-xs font-mono">
                  {clipDuration !== null
                    ? <><span className="text-amber-600 font-bold">{fmtTime(selStart)}</span><span className="mx-1 text-slate-400">→</span><span className="text-amber-600 font-bold">{fmtTime(selStart + clipDuration)}</span></>
                    : <span className="text-slate-700 font-semibold">{fmtTime(currentTime)}</span>}
                  <span className="mx-1 text-slate-400">/</span>
                  <span className="text-slate-500">{fmtTime(duration)}</span>
                </span>
              </div>

              {/* Clip duration */}
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-slate-400">Clip duration:</span>
                <div className="flex rounded-lg border border-slate-200 overflow-hidden">
                  {([30, 60] as const).map(d => (
                    <button key={d} onClick={() => handleClipDurationToggle(d)}
                      className={`px-3 py-1 text-xs font-semibold transition-all ${clipDuration === d ? "bg-[#1a73e8] text-white" : "bg-white text-slate-600 hover:bg-slate-100"}`}>
                      {d}s{clipDuration === d && " ✓"}
                    </button>
                  ))}
                </div>
                {clipDuration !== null && (
                  <button onClick={() => setClipDuration(null)} className="text-[10px] text-slate-400 hover:text-red-500 px-1">✕</button>
                )}
              </div>
            </div>

            {/* Tick ruler */}
            <div className="relative h-5 bg-slate-50 border-b border-slate-200 pointer-events-none overflow-hidden">
              {duration > 0 && Array.from({ length: Math.ceil(duration / tickInterval) + 1 }).map((_, i) => {
                const t = i * tickInterval, pct = (t / duration) * 100
                if (pct > 100) return null
                return (
                  <div key={i} className="absolute top-0 flex flex-col items-center" style={{ left: `${pct}%` }}>
                    <div className="w-px h-2 bg-slate-300" />
                    <span className="text-[9px] text-slate-400 mt-0.5 pl-0.5 whitespace-nowrap">{fmtTime(t)}</span>
                  </div>
                )
              })}
              {duration > 0 && <div className="absolute top-0 bottom-0 w-px bg-red-400" style={{ left: `${playheadPct}%` }} />}
            </div>

            {/* Filmstrip */}
            <div ref={timelineRef} onClick={handleTimelineClick} className="relative overflow-hidden"
              style={{ height: 80, background: "linear-gradient(to bottom,#1a1a2e,#16213e)", cursor: "crosshair" }}>
              <div className="absolute inset-0 flex pointer-events-none">
                {Array.from({ length: 40 }).map((_, i) => <div key={i} className="flex-1 border-r border-white/5" />)}
              </div>
              {project?.thumbnail_url && duration > 0 && (
                <div className="absolute inset-0 flex overflow-hidden opacity-20 pointer-events-none">
                  {Array.from({ length: 24 }).map((_, i) => (
                    <div key={i} className="flex-1 flex-shrink-0 bg-cover bg-center border-r border-black/20"
                      style={{ backgroundImage: `url(${project.thumbnail_url})` }} />
                  ))}
                </div>
              )}
              {duration > 0 && clips.map(clip => {
                const cs = ((clip.start_time || 0) / duration) * 100
                const cw = (((clip.end_time || 0) - (clip.start_time || 0)) / duration) * 100
                return (
                  <div key={clip.id || clip._id}
                    className="absolute top-2 bottom-2 rounded bg-[#1a73e8]/40 border border-[#1a73e8]/70 pointer-events-none"
                    style={{ left: `${cs}%`, width: `${cw}%` }}>
                    <div className="h-full flex items-center justify-center">
                      <span className="text-[9px] text-white/80 font-medium truncate px-1">{fmtTime(clip.start_time||0)}–{fmtTime(clip.end_time||0)}</span>
                    </div>
                  </div>
                )
              })}
              {duration > 0 && splitPoints.map(pt => (
                <div key={pt} className="absolute top-0 bottom-0 z-20 pointer-events-none" style={{ left: `${(pt/duration)*100}%` }}>
                  <div className="w-0.5 h-full bg-yellow-400 opacity-90" />
                  <div className="absolute top-0 -translate-x-[3px]"
                    style={{ width:0,height:0,borderLeft:"4px solid transparent",borderRight:"4px solid transparent",borderTop:"7px solid #facc15" }} />
                  <span className="absolute top-2 left-1 text-[8px] text-yellow-300 font-mono whitespace-nowrap">{fmtTime(pt)}</span>
                </div>
              ))}
              {clipDuration !== null && duration > 0 && (
                <>
                  <div className="absolute top-0 bottom-0 pointer-events-none z-10"
                    style={{ left:0, width:`${selPctStart}%`, background:"rgba(0,0,0,0.55)" }} />
                  <div className="absolute top-0 bottom-0 pointer-events-none z-10"
                    style={{ left:`${selPctStart+selPctWidth}%`, right:0, background:"rgba(0,0,0,0.55)" }} />
                </>
              )}
              {clipDuration !== null && duration > 0 && (
                <div className="absolute top-0 bottom-0 z-20"
                  style={{ left:`${selPctStart}%`, width:`${selPctWidth}%`, border:"2px solid #fbbf24",
                    boxShadow:"0 0 0 1px rgba(251,191,36,.35),inset 0 0 24px rgba(251,191,36,.06)", cursor:"grab" }}
                  onMouseDown={handleSelBoxMouseDown}>
                  {/* Left handle */}
                  <div className="absolute left-0 top-0 bottom-0 z-30 flex items-center justify-center"
                    style={{ width:14, background:"#fbbf24", borderRadius:"2px 0 0 2px", cursor:"ew-resize" }}
                    onMouseDown={handleHandleMouseDown}>
                    <div className="flex flex-col gap-[3px]">
                      <div className="w-[2px] h-3 bg-black/50 rounded-full" /><div className="w-[2px] h-3 bg-black/50 rounded-full" />
                    </div>
                  </div>
                  {/* Right handle */}
                  <div className="absolute right-0 top-0 bottom-0 z-30 flex items-center justify-center"
                    style={{ width:14, background:"#fbbf24", borderRadius:"0 2px 2px 0", cursor:"ew-resize" }}
                    onMouseDown={handleHandleMouseDown}>
                    <div className="flex flex-col gap-[3px]">
                      <div className="w-[2px] h-3 bg-black/50 rounded-full" /><div className="w-[2px] h-3 bg-black/50 rounded-full" />
                    </div>
                  </div>
                  <div className="absolute inset-x-4 inset-y-0 flex items-center justify-between pointer-events-none px-1">
                    <span className="text-[10px] font-bold text-black bg-[#fbbf24] rounded px-1.5 py-0.5 shadow leading-none whitespace-nowrap">{fmtTime(selStart)}</span>
                    <span className="text-[10px] font-bold text-black bg-[#fbbf24]/80 rounded px-1.5 py-0.5 shadow leading-none">{clipDuration}s</span>
                    <span className="text-[10px] font-bold text-black bg-[#fbbf24] rounded px-1.5 py-0.5 shadow leading-none whitespace-nowrap">{fmtTime(selStart+clipDuration)}</span>
                  </div>
                </div>
              )}
              {duration > 0 && (
                <div className="absolute top-0 bottom-0 z-30 flex flex-col items-center"
                  style={{ left:`${playheadPct}%`, transform:"translateX(-50%)", width:16, cursor:"col-resize", pointerEvents: isYT ? "none" : "auto" }}
                  onMouseDown={handlePlayheadMouseDown}>
                  <div className="flex-shrink-0" style={{ width:0,height:0,borderLeft:"6px solid transparent",borderRight:"6px solid transparent",borderTop:"10px solid white" }} />
                  <div className="flex-1 w-[2px] bg-white opacity-80" />
                </div>
              )}
              {duration === 0 && (
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <p className="text-xs text-white/30">Loading timeline…</p>
                </div>
              )}
            </div>

            {/* Info bar */}
            <div className="flex items-center justify-between px-4 h-7 bg-slate-50 border-t border-slate-200 text-[10px]">
              <span className="text-slate-500">
                {clipDuration !== null
                  ? <><span className="font-semibold text-slate-700">{fmtTime(selStart)} → {fmtTime(selStart+clipDuration)}</span><span className="ml-1 text-slate-400">({clipDuration}s)</span></>
                  : <span className="text-slate-400">No clip duration selected — click 30s or 60s to start</span>}
              </span>
              <span className="text-slate-400">{clipDuration !== null ? `Drag the yellow box to choose any ${clipDuration}s segment` : ""}</span>
              <span className="text-slate-500">Total: <span className="font-semibold text-slate-700">{fmtTime(duration)}</span>
                {splitPoints.length > 0 && <span className="ml-2 text-amber-500">{splitPoints.length} split{splitPoints.length > 1?"s":""}</span>}
              </span>
            </div>
          </div>
        </div>

        {/* ── RIGHT PANEL ── */}
        <div className={`flex flex-col flex-shrink-0 border-l border-slate-200 bg-white transition-all duration-200 ${rightPanelOpen ? "w-[300px]" : "w-9"}`}>
          <div className="flex items-center h-10 border-b border-slate-200 flex-shrink-0 px-2">
            {rightPanelOpen && (
              <div className="flex flex-1">
                {(["captions","broll","templates"] as SidePanel[]).map(p => (
                  <button key={p} onClick={() => setSidePanel(p)}
                    className={`flex-1 text-[11px] font-semibold py-1 border-b-2 transition-colors ${sidePanel===p?"text-[#1a73e8] border-[#1a73e8]":"text-slate-500 border-transparent hover:text-slate-900"}`}>
                    {p==="broll"?"B-Roll":p.charAt(0).toUpperCase()+p.slice(1)}
                  </button>
                ))}
              </div>
            )}
            <button onClick={() => setRightPanelOpen(p => !p)}
              className="flex items-center justify-center w-7 h-7 rounded text-slate-400 hover:text-slate-900 hover:bg-slate-100 ml-auto flex-shrink-0">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={rightPanelOpen?"M9 5l7 7-7 7":"M15 19l-7-7 7-7"} />
              </svg>
            </button>
          </div>

          {rightPanelOpen && (
            <div className="flex-1 overflow-y-auto p-3">

              {/* ── CAPTIONS ── */}
              {sidePanel === "captions" && (
                <div className="space-y-3">
                  <p className="text-[11px] text-slate-500">Add captions and map them to a specific clip.</p>

                  {/* Font picker */}
                  <div ref={fontPickerRef} className="relative">
                    <p className="mb-1 text-[10px] font-semibold uppercase text-slate-500">Caption Font ({ALL_FONTS.length} fonts)</p>
                    <button onClick={() => setShowFontPicker(p => !p)}
                      className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-xs hover:border-slate-300 bg-white transition-colors">
                      <span style={{ fontFamily: selectedFont.family }} className="text-slate-900">{selectedFont.label}</span>
                      <svg className={`w-3.5 h-3.5 text-slate-400 transition-transform ${showFontPicker?"rotate-180":""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    {showFontPicker && (
                      <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-72 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-2xl">
                        <div className="sticky top-0 border-b border-slate-200 bg-white p-2">
                          <input autoFocus value={fontSearch} onChange={e => setFontSearch(e.target.value)}
                            placeholder="Search fonts…" className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs outline-none focus:border-[#1a73e8]" />
                        </div>
                        {filteredFonts ? (
                          filteredFonts.length === 0
                            ? <p className="px-3 py-4 text-center text-xs text-slate-400">No fonts found.</p>
                            : filteredFonts.map(font => (
                              <button key={font.label} onClick={() => { setSelectedFont(font); setShowFontPicker(false); setFontSearch("") }}
                                className={`flex w-full items-center justify-between px-3 py-2 text-xs hover:bg-slate-50 ${selectedFont.label===font.label?"text-[#1a73e8] bg-blue-50":"text-slate-700"}`}>
                                <span style={{ fontFamily: font.family }}>{font.label}</span>
                                <span className="text-[10px] text-slate-400" style={{ fontFamily: font.family }}>Abc 123</span>
                              </button>
                            ))
                        ) : FONT_CATEGORIES.map(cat => (
                          <div key={cat.label}>
                            <p className="sticky top-[42px] border-b border-slate-100 bg-slate-50 px-3 py-1.5 text-[10px] font-bold uppercase text-slate-500">{cat.label}</p>
                            {cat.fonts.map(font => (
                              <button key={font.label} onClick={() => { setSelectedFont(font); setShowFontPicker(false); setFontSearch("") }}
                                className={`flex w-full items-center justify-between px-3 py-2 text-xs hover:bg-slate-50 ${selectedFont.label===font.label?"text-[#1a73e8] bg-blue-50":"text-slate-700"}`}>
                                <span style={{ fontFamily: font.family }}>{font.label}</span>
                                <span className="text-[10px] text-slate-400" style={{ fontFamily: font.family }}>Abc 123</span>
                              </button>
                            ))}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Caption colour — compact dropdown */}
                  <div>
                    <p className="mb-1 text-[10px] font-semibold uppercase text-slate-500">Caption Colors</p>
                    <ColorPickerDropdown
                      textColor={captionTextColor} bgColor={captionBgColor} bgOpacity={captionBgOpacity}
                      onTextColor={setCaptionTextColor} onBgColor={setCaptionBgColor} onBgOpacity={setCaptionBgOpacity}
                    />
                  </div>

                  {/* Live preview */}
                  <div className="rounded-lg border border-slate-200 bg-slate-900 px-3 py-4 flex items-end justify-center min-h-[72px] relative overflow-hidden">
                    <div className="absolute inset-0 opacity-20 pointer-events-none"
                      style={{ backgroundImage:"repeating-conic-gradient(#444 0% 25%,#333 0% 50%)", backgroundSize:"12px 12px" }} />
                    <div className="relative rounded px-3 py-1.5 text-sm font-semibold text-center max-w-full"
                      style={{ color:captionTextColor, backgroundColor:captionBgWithAlpha, fontFamily:selectedFont.family }}>
                      {captionText || "This is how your captions will look"}
                    </div>
                  </div>
                  <p className="text-[10px] text-slate-400 text-center -mt-1">Font: {selectedFont.label}</p>

                  {/* Caption Scope */}
                  <div>
                    <p className="mb-1.5 text-[10px] font-semibold uppercase text-slate-500">Caption Scope</p>
                    <div className="flex rounded-lg border border-slate-200 overflow-hidden">
                      <button onClick={() => { setCaptionMode("global"); setSelectedCaptionClipId("") }}
                        className={`flex-1 py-2 text-[11px] font-semibold transition-all ${captionMode==="global"?"bg-[#1a73e8] text-white":"text-slate-600 hover:bg-slate-50"}`}>
                        🌐 All Clips
                      </button>
                      <button onClick={() => setCaptionMode("per_clip")}
                        className={`flex-1 py-2 text-[11px] font-semibold transition-all ${captionMode==="per_clip"?"bg-[#1a73e8] text-white":"text-slate-600 hover:bg-slate-50"}`}>
                        🎬 Per Clip
                      </button>
                    </div>
                    <p className="mt-1 text-[10px] text-slate-400">
                      {captionMode==="global" ? "Same caption applies to all clips." : "Choose a specific clip for this caption."}
                    </p>
                  </div>

                  {/* Caption form */}
                  <form onSubmit={handleSaveCaption} className="space-y-2">
                    {captionMode === "per_clip" && (
                      <select value={selectedCaptionClipId} onChange={e => setSelectedCaptionClipId(e.target.value)}
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-[#1a73e8] bg-white">
                        <option value="">Select a clip…</option>
                        {clips.map(clip => {
                          const id = clip.id || clip._id || ""
                          return <option key={id} value={id}>{clip.label || `Clip ${fmtTime(clip.start_time||0)} – ${fmtTime(clip.end_time||0)}`}</option>
                        })}
                      </select>
                    )}
                    {captionMode === "global" && clips.length === 0 && (
                      <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[11px] text-amber-600">
                        No clips yet. Create a clip first, then add captions.
                      </div>
                    )}
                    <textarea value={captionText} onChange={e => setCaptionText(e.target.value)} rows={3}
                      placeholder="Paste or type captions here..."
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-[#1a73e8] resize-none bg-white"
                      style={{ fontFamily: selectedFont.family }} />
                    <div className="flex gap-2">
                      <label className="cursor-pointer rounded-lg border border-slate-200 px-2 py-1.5 text-[11px] text-slate-600 hover:bg-slate-50 flex-shrink-0">
                        Upload .srt / .txt
                        <input type="file" accept=".txt,.srt,.vtt" className="hidden"
                          onChange={async e => { const f = e.target.files?.[0]; if (f) setCaptionText(await f.text()); e.target.value = "" }} />
                      </label>
                      <button type="submit"
                        disabled={isSavingCaption || !captionText.trim() || (captionMode==="per_clip" && !selectedCaptionClipId)}
                        className="flex-1 rounded-lg bg-[#1a73e8] py-1.5 text-[11px] font-semibold text-white disabled:opacity-50 hover:bg-[#1557b0]">
                        {isSavingCaption ? "Saving…" : "Save Caption"}
                      </button>
                    </div>
                  </form>

                  {/* Saved captions */}
                  <div>
                    <p className="text-[10px] font-semibold uppercase text-slate-500 mb-2">Saved ({captions.length})</p>
                    {captions.length === 0
                      ? <p className="text-[11px] text-slate-400">No captions yet.</p>
                      : captions.map(cap => {
                        const cId = cap.id || cap._id || ""
                        return (
                          <div key={cId} className="mb-2 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
                            {editingCaptionId === cId ? (
                              <div className="space-y-1.5">
                                <textarea value={editingText} onChange={e => setEditingText(e.target.value)} rows={2}
                                  className="w-full rounded border border-slate-200 px-2 py-1 text-[11px] outline-none focus:border-[#1a73e8] bg-white" />
                                <div className="flex gap-1.5">
                                  <button onClick={() => handleUpdateCaption(cId)} className="rounded bg-[#1a73e8] px-2 py-0.5 text-[10px] font-semibold text-white">Save</button>
                                  <button onClick={() => setEditingCaptionId(null)} className="rounded border border-slate-200 px-2 py-0.5 text-[10px] text-slate-600">Cancel</button>
                                </div>
                              </div>
                            ) : (
                              <>
                                <p className="line-clamp-2 text-[11px] text-slate-700" style={{ fontFamily: selectedFont.family }}>{cap.raw_text}</p>
                                <div className="mt-1.5 flex justify-between text-[10px] text-slate-400">
                                  <span>{cap.clip_id ? `Clip: …${cap.clip_id.slice(-6)}` : "🌐 All clips"}</span>
                                  <div className="flex gap-2">
                                    <button onClick={() => { setEditingCaptionId(cId); setEditingText(cap.raw_text||"") }} className="text-[#1a73e8] hover:underline">Edit</button>
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
                    <button onClick={() => setShowGallery(false)} className={`flex-1 py-1.5 text-[11px] font-semibold ${!showGallery?"bg-[#1a73e8] text-white":"text-slate-600 hover:bg-slate-50"}`}>Search</button>
                    <button onClick={() => { setShowGallery(true); loadSavedAssets() }} className={`flex-1 py-1.5 text-[11px] font-semibold ${showGallery?"bg-[#1a73e8] text-white":"text-slate-600 hover:bg-slate-50"}`}>Gallery ({savedAssets.length})</button>
                  </div>
                  {saveMessage && <p className="text-[11px] text-emerald-500 font-medium">{saveMessage}</p>}
                  {!showGallery ? (
                    <>
                      <form onSubmit={handleSearchAssets} className="space-y-2">
                        <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search stock images…"
                          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-[#1a73e8] bg-white" />
                        <div className="flex gap-2">
                          <select value={searchSource} onChange={e => setSearchSource(e.target.value as "all"|"pexels"|"pixabay")}
                            className="rounded-lg border border-slate-200 px-2 py-1.5 text-[11px] bg-white">
                            <option value="all">All</option><option value="pexels">Pexels</option><option value="pixabay">Pixabay</option>
                          </select>
                          <button type="submit" disabled={isSearching}
                            className="flex-1 rounded-lg bg-slate-900 py-1.5 text-[11px] font-semibold text-white disabled:opacity-50 hover:bg-slate-700">
                            {isSearching ? "Searching…" : "Search"}
                          </button>
                        </div>
                      </form>
                      <div className="grid grid-cols-2 gap-1.5">
                        {searchResults.length === 0
                          ? <p className="col-span-2 text-[11px] text-slate-400">Search for images to use as B-roll.</p>
                          : searchResults.map(asset => (
                            <div key={`${asset.source}-${asset.source_id}`} className="overflow-hidden rounded-lg border border-slate-200">
                              <div className="aspect-video bg-slate-100">
                                {asset.thumbnail_url ? <img src={asset.thumbnail_url} alt="" className="h-full w-full object-cover" />
                                  : <div className="flex h-full items-center justify-center text-[10px] text-slate-400">No preview</div>}
                              </div>
                              <div className="p-1.5">
                                <button onClick={() => handleSaveAsset(asset)} disabled={savingAssetId===asset.source_id}
                                  className="w-full rounded border border-slate-200 py-1 text-[10px] text-slate-600 hover:bg-slate-50 disabled:opacity-50">
                                  {savingAssetId===asset.source_id?"Saving…":"Save"}
                                </button>
                              </div>
                            </div>
                          ))}
                      </div>
                    </>
                  ) : (
                    <div>
                      <div className="mb-2 flex items-center justify-between">
                        <p className="text-[10px] font-semibold uppercase text-slate-500">Gallery{isSelectMode&&selectedAssetIds.size>0&&<span className="text-slate-400 ml-1">({selectedAssetIds.size})</span>}</p>
                        <div className="flex gap-1.5">
                          {isSelectMode && savedAssets.length > 0 && (
                            <button onClick={handleSelectAll} className="rounded border border-[#1a73e8]/30 px-2 py-0.5 text-[10px] text-[#1a73e8] hover:bg-blue-50">
                              {allSelected?"Deselect All":"Select All"}
                            </button>
                          )}
                          <button onClick={() => { setIsSelectMode(p => !p); setSelectedAssetIds(new Set()) }}
                            className="rounded border border-slate-200 px-2 py-0.5 text-[10px] text-slate-600 hover:bg-slate-50">
                            {isSelectMode?"Cancel":"Select"}
                          </button>
                          {isSelectMode && selectedAssetIds.size > 0 && (
                            <button onClick={handleDeleteSelectedAssets} disabled={isDeletingSelected}
                              className="flex items-center gap-1 rounded border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] text-red-500 hover:bg-red-100 disabled:opacity-50">
                              <TrashIcon className="w-3 h-3" />{isDeletingSelected?"…":`Del (${selectedAssetIds.size})`}
                            </button>
                          )}
                        </div>
                      </div>
                      {savedAssets.length === 0 ? <p className="text-[11px] text-slate-400">No saved images yet.</p>
                        : (
                          <div className="grid grid-cols-2 gap-1.5">
                            {savedAssets.map(asset => {
                              const aid = asset.id || asset._id || ""
                              const preview = asset.thumbnail_url || asset.url
                              const sel = selectedAssetIds.has(aid)
                              return (
                                <div key={aid||asset.url} className={`group relative overflow-hidden rounded-lg border transition-all ${sel?"border-[#1a73e8] ring-1 ring-[#1a73e8]/40":"border-slate-200"}`}>
                                  <button className="w-full"
                                    onClick={() => { if (isSelectMode&&aid) { toggleAssetSel(aid); return } if (asset.url) window.open(asset.url,"_blank","noopener,noreferrer") }}>
                                    <div className="aspect-square bg-slate-100">
                                      {preview ? <img src={preview} alt="" className="h-full w-full object-cover" />
                                        : <div className="flex h-full items-center justify-center text-[10px] text-slate-400">No preview</div>}
                                    </div>
                                  </button>
                                  {isSelectMode && (
                                    <div className="absolute right-1 top-1">
                                      <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold shadow ${sel?"bg-[#1a73e8] text-white":"bg-white/90 border border-slate-300"}`}>{sel?"✓":""}</span>
                                    </div>
                                  )}
                                  {!isSelectMode && aid && (
                                    <button onClick={e => handleDeleteSingleAsset(aid,e)} disabled={deletingAssetId===aid}
                                      className="absolute right-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-white/90 text-red-500 shadow opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-50 disabled:opacity-50">
                                      {deletingAssetId===aid ? <span className="h-3 w-3 animate-spin rounded-full border border-red-400 border-t-transparent" /> : <TrashIcon className="w-3 h-3" />}
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
                  <p className="text-[11px] text-slate-500">Apply caption style and B-roll pattern automatically.</p>
                  {TEMPLATES.map(tmpl => (
                    <button key={tmpl.key} onClick={() => setSelectedTemplate(selectedTemplate===tmpl.key?null:tmpl.key)}
                      className={`w-full rounded-xl border p-3 text-left transition-all ${selectedTemplate===tmpl.key?"border-[#1a73e8] bg-blue-50":"border-slate-200 bg-white hover:border-slate-300"}`}>
                      <div className="flex items-center gap-2">
                        <span className="text-xl">{tmpl.icon}</span>
                        <div><p className="text-xs font-semibold text-slate-900">{tmpl.label}</p><p className="text-[10px] text-slate-500">{tmpl.description}</p></div>
                        {selectedTemplate===tmpl.key && <span className="ml-auto rounded-full bg-[#1a73e8] px-2 py-0.5 text-[9px] font-bold text-white">Selected</span>}
                      </div>
                    </button>
                  ))}
                  {selectedTemplate && <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-600">Template auto-apply coming soon.</div>}
                </div>
              )}

            </div>
          )}
        </div>
      </div>
    </div>
  )
}