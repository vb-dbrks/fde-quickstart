import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { BAD_REASONS, GOOD_REASONS } from "@/components/documents/values";
import { Button } from "@/components/ui/button";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import type { FeedbackReason, Rating, RatingIn } from "@/lib/api";
import { cn } from "@/lib/utils";

type Draft = { rating: boolean; reasons: FeedbackReason[]; comment: string };

/**
 * Thumbs up or down on something the agent wrote. One click sends the rating; the popover that opens
 * lets the user say why - reasons and a comment, which is what makes feedback useful when the team
 * reviews it in MLflow. Ratings are stored on the run's trace (services/feedback.py).
 */
export function RatingControl({
  label,
  current,
  rate,
}: {
  /** What is being rated, for screen readers: "Summary", "this answer". */
  label: string;
  current: Rating | null | undefined;
  rate: (rating: RatingIn, options?: { onSuccess?: () => void }) => void;
}) {
  const [draft, setDraft] = useState<Draft | null>(null);

  function choose(rating: boolean) {
    const keep = current?.rating === rating;
    const next = {
      rating,
      reasons: keep ? current.reasons : [],
      comment: keep ? (current.comment ?? "") : "",
    };
    rate({ rating, reasons: next.reasons, comment: next.comment || null });
    setDraft(next);
  }

  function toggle(reason: FeedbackReason) {
    setDraft(
      (d) =>
        d && {
          ...d,
          reasons: d.reasons.includes(reason)
            ? d.reasons.filter((r) => r !== reason)
            : [...d.reasons, reason],
        },
    );
  }

  function send() {
    if (!draft) return;
    rate(
      { rating: draft.rating, reasons: draft.reasons, comment: draft.comment.trim() || null },
      { onSuccess: () => toast.success("Thanks - this helps improve the agent") },
    );
    setDraft(null);
  }

  const reasons = draft?.rating ? GOOD_REASONS : BAD_REASONS;
  return (
    <Popover open={draft !== null} onOpenChange={(open) => !open && setDraft(null)}>
      <PopoverAnchor asChild>
        <div role="group" aria-label={`Rate ${label}`} className="flex items-center">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            aria-label="Good"
            aria-pressed={current?.rating === true}
            onClick={() => choose(true)}
          >
            <ThumbsUp aria-hidden className={cn(current?.rating === true && "fill-current")} />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            aria-label="Not good"
            aria-pressed={current?.rating === false}
            onClick={() => choose(false)}
          >
            <ThumbsDown aria-hidden className={cn(current?.rating === false && "fill-current")} />
          </Button>
        </div>
      </PopoverAnchor>
      <PopoverContent align="end" className="w-80 space-y-3">
        <p className="text-sm font-medium">
          {draft?.rating ? "What was good?" : "What was wrong?"}{" "}
          <span className="font-normal text-muted-foreground">(optional)</span>
        </p>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(reasons).map(([reason, text]) => {
            const selected = draft?.reasons.includes(reason as FeedbackReason) ?? false;
            return (
              <Button
                key={reason}
                type="button"
                size="sm"
                variant={selected ? "secondary" : "outline"}
                className="h-7 rounded-full px-3 text-xs"
                aria-pressed={selected}
                onClick={() => toggle(reason as FeedbackReason)}
              >
                {text}
              </Button>
            );
          })}
        </div>
        <Textarea
          aria-label="Comment"
          placeholder="Anything else?"
          rows={2}
          maxLength={2_000}
          value={draft?.comment ?? ""}
          onChange={(event) => setDraft((d) => d && { ...d, comment: event.target.value })}
        />
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
            Skip
          </Button>
          <Button size="sm" onClick={send}>
            Send
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
