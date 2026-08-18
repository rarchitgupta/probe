import { Geist_Mono, Inter } from "next/font/google"

import "./globals.css"
import { Providers } from "@/app/providers"
import { AppSidebar } from "@/components/app-sidebar"
import { ThemeProvider } from "@/components/theme-provider"
import { Separator } from "@/components/ui/separator"
import { Toaster } from "@/components/ui/sonner"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" })

const fontMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
})

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(
        "antialiased",
        fontMono.variable,
        "font-sans",
        inter.variable
      )}
    >
      <body>
        <Providers>
          <ThemeProvider>
            <TooltipProvider>
              <SidebarProvider>
                <AppSidebar />
                <SidebarInset>
                  <header className="flex h-16 shrink-0 items-center gap-2 border-b px-3">
                    <SidebarTrigger />
                    <Separator orientation="vertical" className="mx-2" />
                    <span className="font-medium">Probe</span>
                  </header>
                  {children}
                </SidebarInset>
              </SidebarProvider>
              <Toaster />
            </TooltipProvider>
          </ThemeProvider>
        </Providers>
      </body>
    </html>
  )
}
