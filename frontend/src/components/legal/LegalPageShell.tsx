import type { ReactNode } from "react"
import Link from "next/link"
import { DM_Sans, Syne } from "next/font/google"

const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
})

const syne = Syne({
  subsets: ["latin"],
  weight: ["700", "800"],
})

type LegalPageShellProps = {
  title: string
  effectiveDate: string
  children: ReactNode
}

export default function LegalPageShell({ title, effectiveDate, children }: LegalPageShellProps) {
  return (
    <div className={`${dmSans.className} min-h-screen bg-[#faf8ff] text-[#191b23]`}>
      <header className="border-b border-[#c3c6d7]/60 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
          <Link href="/login" className="flex items-center gap-2 no-underline">
            <div className="h-5 w-1 bg-[#2563eb]" />
            <span className={`${syne.className} text-xl font-extrabold tracking-tight text-[#191b23]`}>
              Movie <span className="text-[#2563eb]">Clips</span>
            </span>
          </Link>
          <nav className="flex gap-4 text-sm text-[#434655]">
            <Link href="/privacy" className="hover:text-[#2563eb]">
              Privacy
            </Link>
            <Link href="/terms" className="hover:text-[#2563eb]">
              Terms
            </Link>
            <Link href="/login" className="hover:text-[#2563eb]">
              Sign in
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1 className={`${syne.className} m-0 text-3xl font-extrabold tracking-tight sm:text-4xl`}>{title}</h1>
        <p className="mt-2 text-sm text-[#434655]">Effective date: {effectiveDate}</p>
        <div className="prose-legal mt-10 space-y-8 text-[15px] leading-relaxed text-[#191b23]">{children}</div>
      </main>

      <footer className="border-t border-[#c3c6d7]/60 bg-white">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3 px-6 py-6 text-sm text-[#434655]">
          <span>© {new Date().getFullYear()} Purple Merit / Movie Clips</span>
          <div className="flex gap-4">
            <Link href="/privacy" className="hover:text-[#2563eb]">
              Privacy Policy
            </Link>
            <Link href="/terms" className="hover:text-[#2563eb]">
              Terms of Service
            </Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

export function LegalSection({
  id,
  title,
  children,
}: {
  id?: string
  title: string
  children: ReactNode
}) {
  return (
    <section id={id} className="scroll-mt-24">
      <h2 className={`${syne.className} mb-3 text-xl font-bold tracking-tight`}>{title}</h2>
      <div className="space-y-3 text-[#434655] [&_a]:text-[#2563eb] [&_a]:underline [&_li]:ml-5 [&_li]:list-disc [&_strong]:font-semibold [&_strong]:text-[#191b23] [&_ul]:space-y-1.5">
        {children}
      </div>
    </section>
  )
}
