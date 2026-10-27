import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, IBM_Plex_Sans_Devanagari } from "next/font/google";
import Script from "next/script";
import { Providers } from "@/components/Providers";
import "./globals.css";

// One family: IBM Plex Sans, with its own Devanagari cut for Hindi, and Plex Mono for one job
// (FDR numbers, IFSCs, hashes).
const plex = IBM_Plex_Sans({ subsets: ["latin"], variable: "--font-plex", weight: ["400", "500", "600"] });
const plexDeva = IBM_Plex_Sans_Devanagari({ subsets: ["devanagari"], variable: "--font-plex-deva", weight: ["400", "500", "600"] });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], variable: "--font-plex-mono", weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "DepositTrack",
  description: "Security deposit and FDR management for the AICTE Regulation Bureau",
};

// Sets the saved or system theme before first paint, so a dark-theme user never sees a white flash.
const THEME_BOOT = `try{var t=localStorage.getItem("dt.theme");if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${plex.variable} ${plexDeva.variable} ${plexMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body>
        <Providers>{children}</Providers>
        <Script src="/charts.js" strategy="afterInteractive" />
      </body>
    </html>
  );
}
