import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { GalacticDomeBackground } from "@/components/galactic-dome-background";
import "./globals.css";

export const metadata: Metadata = {
  title: "OmniDome Customer Portal",
  description: "Manage your connection, billing, and support — powered by OmniDome.",
  manifest: "/manifest.json",
};

export const viewport: Viewport = {
  themeColor: "#6366f1",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <GalacticDomeBackground variant="light" />
        {children}
      </body>
    </html>
  );
}
