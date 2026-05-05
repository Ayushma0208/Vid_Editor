export type JobStatus =
  | "queued"
  | "downloading"
  | "transcribing"
  | "analyzing"
  | "cutting"
  | "reframing"
  | "captioning"
  | "scoring"
  | "done"
  | "failed"

export interface Job {
  id: string
  youtube_url: string
  title: string
  thumbnail: string
  status: JobStatus
  progress: number
  created_at: string
  clip_count?: number
}
