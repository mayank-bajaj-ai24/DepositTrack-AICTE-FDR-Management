import type { Metadata } from "next";
import { Geist, Geist_Mono, Noto_Sans_Devanagari } from "next/font/google";
import Script from "next/script";
import { Providers } from "@/components/Providers";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist", weight: ["400", "500", "600", "700"] });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", weight: ["400", "500"] });
// Hindi text: Geist has no Devanagari, so this face has one job — Devanagari script.
const deva = Noto_Sans_Devanagari({ subsets: ["devanagari"], variable: "--font-deva", weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: "DepositTrack",
  description: "Security deposit and FDR management for the AICTE Regulation Bureau",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${geist.variable} ${geistMono.variable} ${deva.variable}`}>
      <body>
        <Providers>{children}</Providers>
        <Script src="/charts.js" strategy="afterInteractive" />
      </body>
    </html>
  );
}
