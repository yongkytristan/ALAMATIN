import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ALAMATIN — Review Alamat",
  description: "Pemeriksaan alamat Jawa Barat sebelum fulfillment.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
