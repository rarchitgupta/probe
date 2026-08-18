"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { HomeIcon, ListChecksIcon, ScanSearchIcon } from "lucide-react"

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"

const navigation = [
  { title: "Home", url: "/", icon: HomeIcon },
  { title: "Runs", url: "/runs", icon: ListChecksIcon },
]

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const pathname = usePathname()

  return (
    <Sidebar {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<Link href="/" />}>
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                <ScanSearchIcon className="size-4" />
              </div>
              <div className="flex flex-col gap-0.5 leading-none">
                <span className="font-medium">Probe</span>
                <span>Browser QA</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu>
            {navigation.map((item) => (
              <SidebarMenuItem key={item.title}>
                <SidebarMenuButton
                  isActive={
                    item.url === "/"
                      ? pathname === "/"
                      : pathname.startsWith(item.url)
                  }
                  render={<Link href={item.url} />}
                >
                  <item.icon />
                  {item.title}
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  )
}
