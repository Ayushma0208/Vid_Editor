import { create } from "zustand"
import type { Project } from "@/types/project"
import type { Job } from "@/types/job"

interface ProjectState {
  projects: Project[]
  activeJob: Job | null
  setProjects: (p: Project[]) => void
  addProject: (p: Project) => void
  setActiveJob: (j: Job | null) => void
  updateJobStatus: (jobId: string, status: Job["status"], progress: number) => void
}

export const useProjectStore = create<ProjectState>((set) => ({
  projects: [],
  activeJob: null,
  setProjects: (projects) => set({ projects }),
  addProject: (p) => set((s) => ({ projects: [p, ...s.projects] })),
  setActiveJob: (activeJob) => set({ activeJob }),
  updateJobStatus: (jobId, status, progress) =>
    set((s) => ({
      projects: s.projects.map((p) =>
        p.job.id === jobId
          ? { ...p, job: { ...p.job, status, progress } }
          : p
      ),
      activeJob:
        s.activeJob?.id === jobId
          ? { ...s.activeJob, status, progress }
          : s.activeJob,
    })),
}))
