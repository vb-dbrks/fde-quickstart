import type { RouteObject } from "react-router";

import { AppShell } from "@/app/AppShell";
import { RouteError } from "@/app/RouteError";
import { RequirePermission } from "@/components/RequirePermission";
import { AdminRolesPage } from "@/pages/AdminRolesPage";
import { AssistantPage } from "@/pages/AssistantPage";
import { HomePage } from "@/pages/HomePage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { NotesPage } from "@/pages/NotesPage";

/** Add pages here and to NAV_ITEMS (app/nav.ts). FastAPI serves index.html for every path. */
export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "notes", element: <NotesPage /> },
      { path: "assistant", element: <AssistantPage /> },
      {
        path: "admin/roles",
        element: (
          <RequirePermission permission="roles:manage">
            <AdminRolesPage />
          </RequirePermission>
        ),
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
