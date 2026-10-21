import { FileText, LayoutDashboard, ShieldCheck, type LucideIcon } from "lucide-react";

import type { Permission } from "@/lib/api";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Hide the item unless the user has this permission. */
  permission?: Permission;
};

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Home", icon: LayoutDashboard },
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/admin/roles", label: "Users & roles", icon: ShieldCheck, permission: "roles:manage" },
];

/** The page title in index.html (set by `make init`). */
export const APP_TITLE = document.title || "Quickstart App";
