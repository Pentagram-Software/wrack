import type { Metadata } from "next";
import { Bruno_Ace, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/design-system/providers/ThemeProvider";
import { SessionProvider } from "next-auth/react";

const brunoAce = Bruno_Ace({
  variable: "--font-bruno-ace",
  subsets: ["latin"],
  weight: "400",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "WRACK Control Center",
  description: "EV3 robot control interface",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${brunoAce.variable} ${geistMono.variable} antialiased`} suppressHydrationWarning>
        <SessionProvider>
          <ThemeProvider>
            {children}
          </ThemeProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
