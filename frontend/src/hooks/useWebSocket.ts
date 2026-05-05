"use client"
import { useEffect } from "react"
import { getSocket } from "@/lib/socket"
import { useProjectStore } from "@/store/useProjectStore"

export function useWebSocket(jobId: string | null) {
  const updateJobStatus = useProjectStore((s) => s.updateJobStatus)

  useEffect(() => {
    if (!jobId) return
    const socket = getSocket()
    socket.connect()
    socket.emit("subscribe_job", jobId)

    socket.on("job_progress", (data: { job_id: string; status: string; progress: number }) => {
      updateJobStatus(data.job_id, data.status as any, data.progress)
    })

    return () => {
      socket.emit("unsubscribe_job", jobId)
      socket.disconnect()
    }
  }, [jobId, updateJobStatus])
}
