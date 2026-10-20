import { NavLink } from "react-router";

import { APP_TITLE, NAV_ITEMS } from "@/app/nav";
import { usePermissions } from "@/lib/permissions";
import { cn } from "@/lib/utils";

export function Sidebar({ open, onNavigate }: { open: boolean; onNavigate: () => void }) {
  const { can } = usePermissions();
  const items = NAV_ITEMS.filter((item) => !item.permission || can(item.permission));

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 w-60 border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-transform md:static md:translate-x-0",
        open ? "translate-x-0" : "-translate-x-full",
      )}
    >
      <div className="flex h-14 items-center gap-2 border-b border-sidebar-border px-4">
        <img src="/favicon.svg" alt="" className="size-6" />
        <span className="truncate font-semibold">{APP_TITLE}</span>
      </div>
      <nav aria-label="Main" className="flex flex-col gap-1 p-2">
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                isActive && "bg-sidebar-accent text-sidebar-accent-foreground",
              )
            }
          >
            <Icon aria-hidden className="size-4" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
