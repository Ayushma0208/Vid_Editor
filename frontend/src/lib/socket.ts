import { io, Socket } from "socket.io-client"

let socket: Socket | null = null

function socketBaseUrl() {
  if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL
  if (typeof window !== "undefined") return window.location.origin
  return ""
}

export function getSocket(): Socket {
  if (!socket) {
    socket = io(socketBaseUrl(), {
      transports: ["websocket"],
      autoConnect: false,
    })
  }
  return socket
}
