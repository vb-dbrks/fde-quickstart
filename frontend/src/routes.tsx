import type { RouteObject } from "react-router";

import { AppShell } from "@/app/AppShell";
import { RouteError } from "@/app/RouteError";
import { RequirePermission } from "@/components/RequirePermission";
import { AdminRolesPage } from "@/pages/AdminRolesPage";
import { DocumentPage } from "@/pages/DocumentPage";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { HomePage } from "@/pages/HomePage";
import { NotFoundPage } from "@/pages/NotFoundPage";

/** Add pages here and to NAV_ITEMS (app/nav.ts). FastAPI serves index.html for every path. */
export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "documents", element: <DocumentsPage /> },
      { path: "documents/:documentId", element: <DocumentPage /> },
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
