import { DM_Sans, JetBrains_Mono, Syne } from "next/font/google"

export const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  display: "swap",
})

export const syne = Syne({
  subsets: ["latin"],
  weight: ["700", "800"],
  display: "swap",
})

export const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["500", "600"],
  display: "swap",
})
