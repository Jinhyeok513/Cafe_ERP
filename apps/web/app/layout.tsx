import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cafe ERP | Operations",
  description: "Cafe inventory, receiving and stocktake operations dashboard",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
