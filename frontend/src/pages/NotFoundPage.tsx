import { MapPinOff } from "lucide-react";
import { Link } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <EmptyState
      icon={MapPinOff}
      title="Page not found"
      description="The page you're looking for doesn't exist."
      action={
        <Button asChild variant="outline">
          <Link to="/">Go home</Link>
        </Button>
      }
    />
  );
}
