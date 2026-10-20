import { StickyNote, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Can } from "@/components/Can";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { QueryError } from "@/components/QueryError";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type { Note } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useCreateNote, useDeleteNote, useNotes } from "@/lib/queries";

/** Sample feature: replace it with your engagement's own screens. */
export function NotesPage() {
  const [mine, setMine] = useState(false);
  const notes = useNotes(mine);

  return (
    <>
      <PageHeader
        title="Notes"
        description="A sample feature stored in Lakebase. Replace it with your own."
        actions={
          <Button variant={mine ? "secondary" : "outline"} size="sm" onClick={() => setMine(!mine)}>
            {mine ? "Showing only mine" : "Show only mine"}
          </Button>
        }
      />
      <Can
        permission="notes:write"
        fallback={
          <p className="rounded-md bg-muted px-4 py-3 text-sm text-muted-foreground">
            You have read-only access. Ask an admin for the editor role to add notes.
          </p>
        }
      >
        <NewNoteForm />
      </Can>
      {notes.isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : notes.isError ? (
        <QueryError error={notes.error} onRetry={() => notes.refetch()} />
      ) : notes.data.length === 0 ? (
        <EmptyState icon={StickyNote} title="No notes yet" description="New notes show up here." />
      ) : (
        <ul className="space-y-3">
          {notes.data.map((note) => (
            <li key={note.id}>
              <NoteCard note={note} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function NewNoteForm() {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const createNote = useCreateNote();

  function submit(event: FormEvent) {
    event.preventDefault();
    createNote.mutate(
      { title, body },
      {
        onSuccess: () => {
          setTitle("");
          setBody("");
          toast.success("Note added");
        },
        onError: (error) => toast.error(error.message),
      },
    );
  }

  return (
    <Card>
      <form onSubmit={submit} className="contents">
        <CardHeader>
          <CardTitle>New note</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="note-title">Title</Label>
            <Input
              id="note-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={200}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="note-body">Note</Label>
            <Textarea
              id="note-body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
            />
          </div>
        </CardContent>
        <CardFooter>
          <Button type="submit" disabled={createNote.isPending || !title.trim()}>
            {createNote.isPending ? "Saving…" : "Add note"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

function NoteCard({ note }: { note: Note }) {
  const deleteNote = useDeleteNote();

  return (
    <Card className="gap-3">
      <CardHeader>
        <CardTitle>{note.title}</CardTitle>
        <CardDescription>
          {note.owner} · {formatDateTime(note.created_at)}
        </CardDescription>
      </CardHeader>
      {note.body && <CardContent className="text-sm whitespace-pre-wrap">{note.body}</CardContent>}
      {note.can_delete && (
        <CardFooter className="justify-end">
          <Button
            variant="ghost"
            size="sm"
            disabled={deleteNote.isPending}
            onClick={() =>
              deleteNote.mutate(note.id, {
                onSuccess: () => toast.success("Note deleted"),
                onError: (error) => toast.error(error.message),
              })
            }
          >
            <Trash2 aria-hidden /> Delete
          </Button>
        </CardFooter>
      )}
    </Card>
  );
}
