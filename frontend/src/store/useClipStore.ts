import { create } from "zustand"
import type { Clip } from "@/types/clip"

interface ClipState {
  clips: Clip[]
  selectedClip: Clip | null
  setClips: (c: Clip[]) => void
  selectClip: (c: Clip) => void
}

export const useClipStore = create<ClipState>((set) => ({
  clips: [],
  selectedClip: null,
  setClips: (clips) => set({ clips }),
  selectClip: (selectedClip) => set({ selectedClip }),
}))
