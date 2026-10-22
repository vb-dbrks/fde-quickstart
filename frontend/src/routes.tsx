import { examples, ExampleRoute } from "@/examples/registry";
import type { RouteObject } from "react-router";

import { AppShell } from "@/app/AppShell";
import { RouteError } from "@/app/RouteError";
import { RequirePermission } from "@/components/RequirePermission";
import { AdminRolesPage } from "@/pages/AdminRolesPage";
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
      ...examples.flatMap((example) =>
        example.routes.map((route) => ({
          ...route,
          element: <ExampleRoute id={example.id}>{route.element}</ExampleRoute>,
        })),
      ),
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
