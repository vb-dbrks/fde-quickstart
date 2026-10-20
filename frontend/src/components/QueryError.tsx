import { CircleAlert } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";

export function QueryError({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <EmptyState
      icon={CircleAlert}
      tone="error"
      title="Something went wrong"
      description={error.message}
      action={
        onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            Try again
          </Button>
        )
      }
    />
  );
}
