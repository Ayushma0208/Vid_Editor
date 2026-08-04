import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"
import { Toaster } from "@/components/ui/toaster"
import QueryProvider from "@/components/layout/QueryProvider"
 
const inter = Inter({ subsets: ["latin"] })
 
export const metadata: Metadata = {
  title: "Movie Clips — Split long videos into 60-second clips",
  description: "Upload long videos, cut them into 60-second clips, and publish to Instagram with a full-video summary",
}
 
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Abril+Fatface&family=Advent+Pro:wght@400;700&family=Alegreya:wght@400;700&family=Alfa+Slab+One&family=Amatic+SC:wght@400;700&family=Anton&family=Archivo+Black&family=Arimo:wght@400;700&family=Arvo:wght@400;700&family=Asap:wght@400;700&family=Assistant:wght@400;700&family=Audiowide&family=Bangers&family=Barlow:wght@400;700&family=Barlow+Condensed:wght@400;700&family=Bebas+Neue&family=Bitter:wght@400;700&family=Black+Han+Sans&family=Boogaloo&family=Cabin:wght@400;700&family=Cairo:wght@400;700&family=Caveat:wght@400;700&family=Chakra+Petch:wght@400;700&family=Chewy&family=Cinzel:wght@400;700&family=Comfortaa:wght@400;700&family=Comic+Neue:wght@400;700&family=Contrail+One&family=Cormorant+Garamond:wght@400;700&family=Courgette&family=Crete+Round&family=Crimson+Text:wght@400;700&family=Dancing+Script:wght@400;700&family=Didact+Gothic&family=DM+Sans:wght@400;700&family=DM+Serif+Display&family=Dosis:wght@400;700&family=EB+Garamond:wght@400;700&family=Economica:wght@400;700&family=Edu+NSW+ACT+Foundation&family=Exo:wght@400;700&family=Exo+2:wght@400;700&family=Fascinate&family=Figtree:wght@400;700&family=Fjalla+One&family=Fredoka:wght@400;700&family=Gelasio:wght@400;700&family=Graduate&family=Grand+Hotel&family=Gruppo&family=Gugi&family=Hammersmith+One&family=Handlee&family=Hind:wght@400;700&family=IBM+Plex+Mono:wght@400;700&family=IBM+Plex+Sans:wght@400;700&family=IBM+Plex+Serif:wght@400;700&family=Inconsolata:wght@400;700&family=Indie+Flower&family=Josefin+Sans:wght@400;700&family=Josefin+Slab:wght@400;700&family=Jost:wght@400;700&family=Julius+Sans+One&family=Kanit:wght@400;700&family=Karla:wght@400;700&family=Kaushan+Script&family=Khand:wght@400;700&family=Knewave&family=Lalezar&family=Lato:wght@400;700&family=League+Gothic&family=Lexend:wght@400;700&family=Libre+Baskerville:wght@400;700&family=Libre+Franklin:wght@400;700&family=Lilita+One&family=Lobster&family=Lobster+Two:wght@400;700&family=Lora:wght@400;700&family=Luckiest+Guy&family=Manrope:wght@400;700&family=Marcellus&family=Maven+Pro:wght@400;700&family=Merriweather:wght@400;700&family=Michroma&family=Montserrat:wght@400;700&family=Mountains+of+Christmas:wght@400;700&family=Mukta:wght@400;700&family=Mulish:wght@400;700&family=Nanum+Gothic:wght@400;700&family=Neucha&family=Neuton:wght@400;700&family=Noticia+Text:wght@400;700&family=Nunito:wght@400;700&family=Nunito+Sans:wght@400;700&family=Old+Standard+TT:wght@400;700&family=Open+Sans:wght@400;700&family=Orbitron:wght@400;700&family=Oswald:wght@400;700&family=Outfit:wght@400;700&family=Overpass:wght@400;700&family=Oxygen:wght@400;700&family=Pacifico&family=Patrick+Hand&family=Patua+One&family=Paytone+One&family=Permanent+Marker&family=Philosopher:wght@400;700&family=Play:wght@400;700&family=Playfair+Display:wght@400;700&family=Plus+Jakarta+Sans:wght@400;700&family=Poiret+One&family=Poppins:wght@400;700&family=Prompt:wght@400;700&family=PT+Mono&family=PT+Sans:wght@400;700&family=PT+Serif:wght@400;700&family=Quicksand:wght@400;700&family=Rajdhani:wght@400;700&family=Raleway:wght@400;700&family=Readex+Pro:wght@400;700&family=Righteous&family=Roboto:wght@400;700&family=Roboto+Condensed:wght@400;700&family=Roboto+Mono:wght@400;700&family=Roboto+Slab:wght@400;700&family=Rokkitt:wght@400;700&family=Rosario:wght@400;700&family=Rowdies:wght@400;700&family=Rubik:wght@400;700&family=Russo+One&family=Sacramento&family=Satisfy&family=Sawarabi+Gothic&family=Share+Tech+Mono&family=Sigmar&family=Signika:wght@400;700&family=Silkscreen&family=Slabo+27px&family=Source+Code+Pro:wght@400;700&family=Source+Sans+3:wght@400;700&family=Source+Serif+4:wght@400;700&family=Space+Mono:wght@400;700&family=Special+Elite&family=Spectral:wght@400;700&family=Squada+One&family=Stint+Ultra+Expanded&family=Syncopate:wght@400;700&family=Teko:wght@400;700&family=Titillium+Web:wght@400;700&family=Tourney:wght@400;700&family=Ubuntu:wght@400;700&family=Ubuntu+Mono:wght@400;700&family=Ultra&family=Unbounded:wght@400;700&family=Unna:wght@400;700&family=Urbanist:wght@400;700&family=Varela+Round&family=Viga&family=Vollkorn:wght@400;700&family=Voltaire&family=Work+Sans:wght@400;700&family=Yanone+Kaffeesatz:wght@400;700&family=Yantramanav:wght@400;700&family=Yeseva+One&family=Zilla+Slab:wght@400;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className={`${inter.className} bg-white text-zinc-900 antialiased`}>
        <QueryProvider>
          {children}
          <Toaster />
        </QueryProvider>
      </body>
    </html>
  )
}