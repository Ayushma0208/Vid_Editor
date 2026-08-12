export interface Clip {
  id: string
  job_id: string
  title: string
  start_time: number
  end_time: number
  duration: number
  interest_score?: number | null
  is_recommended?: boolean
  viral_score?: number
  file_url: string
  thumbnail_url: string
  captions: Caption[]
  broll_segments: BRollSegment[]
  platform_format: "9:16" | "16:9" | "1:1"
}

export interface Caption {
  id: string
  start: number
  end: number
  text: string
}

export interface BRollSegment {
  id: string
  start: number
  end: number
  asset_url: string
  asset_type: "video" | "image"
}
