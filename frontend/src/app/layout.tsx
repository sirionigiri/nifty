import type { Metadata } from "next"
import { GeistSans } from "geist/font/sans" // This is the premium font we selected!
import "./globals.css"
import { ThemeProvider } from "@/components/ThemeProvider"
import { QueryProvider } from "@/components/QueryProvider"

export const metadata: Metadata = {
  title: "NSE Index Screener",
  description: "Advanced financial index screener and analytics",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    // suppressHydrationWarning is required for next-themes to work perfectly
    <html lang="en" suppressHydrationWarning>
      <body className={`${GeistSans.className} antialiased`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <QueryProvider>
            {children}
          </QueryProvider>
        </ThemeProvider>

      </body>
    </html>
  )
}