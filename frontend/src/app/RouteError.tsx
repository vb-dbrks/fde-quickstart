import { TriangleAlert } from "lucide-react";
import { isRouteErrorResponse, useRouteError } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";

/** Shown when rendering a route throws. */
export function RouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : "Unknown error";

  return (
    <div className="mx-auto max-w-lg p-6">
      <EmptyState
        icon={TriangleAlert}
        tone="error"
        title="This page crashed"
        description={message}
        action={<Button onClick={() => window.location.reload()}>Reload</Button>}
      />
    </div>
  );
}
