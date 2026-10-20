import { Menu } from "lucide-react";
import { useState } from "react";
import { Outlet } from "react-router";

import { NotificationBell } from "@/app/NotificationBell";
import { Sidebar } from "@/app/Sidebar";
import { UserMenu } from "@/app/UserMenu";
import { Button } from "@/components/ui/button";

/** Layout for every page: sidebar navigation, header with notifications and account menu. */
export function AppShell() {
  const [navOpen, setNavOpen] = useState(false);

  return (
    <div className="flex min-h-svh">
      <Sidebar open={navOpen} onNavigate={() => setNavOpen(false)} />
      {navOpen && (
        <div
          aria-hidden
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
          onClick={() => setNavOpen(false)}
        />
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-2 border-b px-4">
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label="Open navigation"
            onClick={() => setNavOpen(true)}
          >
            <Menu aria-hidden />
          </Button>
          <div className="ml-auto flex items-center gap-1">
            <NotificationBell />
            <UserMenu />
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 space-y-6 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
