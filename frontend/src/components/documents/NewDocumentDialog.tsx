import { Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { fromText, isEmpty } from "@/components/documents/values";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { keyed, type DocumentType } from "@/lib/api";
import { useCreateDocument } from "@/lib/queries";

/**
 * Create a document of ``documentType``. The form is built from the field catalog: it asks for the
 * user fields only, and the agent fills in the rest.
 */
export function NewDocumentDialog({ documentType }: { documentType: DocumentType }) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const create = useCreateDocument();
  const navigate = useNavigate();
  const userFields = documentType.fields.filter((field) => !field.agent_generates);
  const complete = userFields.every((field) => !field.required || values[field.field_path]?.trim());

  function submit(event: FormEvent) {
    event.preventDefault();
    // Each value takes its field's catalog type: list fields become arrays (one item per line).
    const fields = Object.fromEntries(
      userFields
        .map((field) => [field.field_path, fromText(field.type, values[field.field_path] ?? "")])
        .filter(([, value]) => !isEmpty(value)),
    );
    create.mutate(keyed({ document_type: documentType.name, fields }), {
      onSuccess: (document) => {
        setOpen(false);
        setValues({});
        navigate(`/documents/${document.id}`);
      },
      onError: (error) => toast.error(error.message),
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus aria-hidden /> New {documentType.label.toLowerCase()}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit} className="contents">
          <DialogHeader>
            <DialogTitle>New {documentType.label.toLowerCase()}</DialogTitle>
            <DialogDescription>{documentType.description}</DialogDescription>
          </DialogHeader>
          {userFields.map((field) => {
            const id = `new-${field.field_path}`;
            const props = {
              id,
              value: values[field.field_path] ?? "",
              required: field.required,
              onChange: (event: { target: { value: string } }) =>
                setValues((current) => ({ ...current, [field.field_path]: event.target.value })),
            };
            return (
              <div key={field.field_path} className="space-y-1.5">
                <Label htmlFor={id}>{field.label}</Label>
                {field.field_path.endsWith(".title") ? (
                  <Input {...props} maxLength={200} />
                ) : (
                  <Textarea {...props} rows={field.type === "list" ? 4 : 3} />
                )}
                {field.type === "list" && (
                  <p className="text-xs text-muted-foreground">One item per line.</p>
                )}
                <p className="text-xs text-muted-foreground">{field.description}</p>
              </div>
            );
          })}
          <DialogFooter>
            <Button type="submit" disabled={create.isPending || !complete}>
              {create.isPending ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
