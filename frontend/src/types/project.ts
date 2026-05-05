export interface Project {
  id: string
  user_id: string
  youtube_url: string
  title: string
  thumbnail: string
  created_at: string
  job: import("./job").Job
  clips: import("./clip").Clip[]
}
