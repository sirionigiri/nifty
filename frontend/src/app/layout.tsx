import type { Metadata } from "next"
import { GeistSans } from "geist/font/sans"
import "./globals.css"
import { ThemeProvider } from "@/components/ThemeProvider"
import { QueryProvider } from "@/components/QueryProvider"
import { Toaster } from "@/components/ui/sonner"

export const metadata: Metadata = {
  metadataBase: new URL("https://YOUR-VERCEL-URL.vercel.app"),

  title: "NSE Index Screener",
  description: "Advanced financial index screener and analytics",

  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },

  openGraph: {
    title: "NSE Index Screener",
    description: "Advanced financial index screener and analytics",
    url: "/",
    siteName: "NSE Index Screener",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 1200,
        alt: "NSE Index Screener",
      },
    ],
    locale: "en_US",
    type: "website",
  },

  twitter: {
    card: "summary_large_image",
    title: "NSE Index Screener",
    description: "Advanced financial index screener and analytics",
    images: ["/og-image.png"],
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${GeistSans.className} antialiased`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem={false}
          disableTransitionOnChange
        >
          <QueryProvider>
            {children}
            <Toaster position="top-right" richColors />
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}