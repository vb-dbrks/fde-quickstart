import { Share2, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ACCESS_LABELS } from "@/components/documents/values";
import { NativeSelect } from "@/components/ui/native-select";
import type { Access } from "@/lib/api";
import { useDocumentAccess, useShareDocument, useUnshareDocument } from "@/lib/queries";

/** Owners share a document with other people (view, edit or owner access). */
export function ShareDialog({ documentId }: { documentId: string }) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [access, setAccess] = useState<Access>("view");
  const entries = useDocumentAccess(documentId, open);
  const share = useShareDocument(documentId);
  const unshare = useUnshareDocument(documentId);

  function submit(event: FormEvent) {
    event.preventDefault();
    share.mutate(
      { email: email.trim(), access },
      {
        onSuccess: () => {
          toast.success(`Shared with ${email.trim()}`);
          setEmail("");
        },
        onError: (error) => toast.error(error.message),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Share2 aria-hidden /> Share
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Share this document</DialogTitle>
          <DialogDescription>
            People need the editor role to edit or run the agent, whatever access they have here.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-wrap gap-2">
          <Input
            type="email"
            aria-label="Email"
            placeholder="name@example.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="min-w-48 flex-1"
            required
          />
          <NativeSelect
            aria-label="Access"
            value={access}
            onChange={(event) => setAccess(event.target.value as Access)}
          >
            {Object.entries(ACCESS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </NativeSelect>
          <Button type="submit" disabled={share.isPending || !email.trim()}>
            Share
          </Button>
        </form>
        <ul aria-label="People with access" className="divide-y text-sm">
          {entries.data?.map((entry) => (
            <li key={entry.principal} className="flex items-center justify-between gap-2 py-2">
              <span className="min-w-0 truncate">{entry.principal}</span>
              <span className="flex items-center gap-1 text-muted-foreground">
                {ACCESS_LABELS[entry.access]}
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-7"
                  aria-label={`Remove ${entry.principal}`}
                  disabled={unshare.isPending}
                  onClick={() =>
                    unshare.mutate(entry.principal, {
                      onError: (error) => toast.error(error.message),
                    })
                  }
                >
                  <Trash2 aria-hidden />
                </Button>
              </span>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
