import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { Interaction } from "@/agent/AgentProvider";

export function RunActivity({ interaction }: { interaction: Interaction }) {
  return (
    <div className="space-y-2" aria-live="polite">
      <p className="text-sm text-muted-foreground">
        {interaction.error
          ? "Could not complete this request"
          : interaction.finished
            ? "Ready"
            : "Working…"}
      </p>
      {interaction.error && (
        <p role="alert" className="text-sm text-destructive">
          {interaction.error}
        </p>
      )}
      <ToolActivity events={interaction.toolEvents} />
      {import.meta.env.DEV && (
        <details className="text-xs text-muted-foreground">
          <summary>Interaction events</summary>
          <ol className="max-h-40 overflow-auto">
            {interaction.events.map((event, i) => (
              <li key={i}>
                <details>
                  <summary>
                    {i + 1} · {event.type}
                  </summary>
                  <pre className="overflow-x-auto">{JSON.stringify(event, null, 2)}</pre>
                </details>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
export function StructuredResult({ value }: { value: unknown }) {
  if (value === null || value === undefined) return null;
  if (Array.isArray(value))
    return (
      <ul className="list-inside list-disc space-y-1">
        {value.map((item, i) => (
          <li key={i}>
            <StructuredResult value={item} />
          </li>
        ))}
      </ul>
    );
  if (typeof value === "object")
    return (
      <dl className="space-y-3">
        {Object.entries(value).map(([key, item]) => (
          <div key={key}>
            <dt className="text-xs font-medium text-muted-foreground uppercase">
              {key.replaceAll("_", " ")}
            </dt>
            <dd>
              <StructuredResult value={item} />
            </dd>
          </div>
        ))}
      </dl>
    );
  return <span className="whitespace-pre-wrap">{String(value)}</span>;
}
export function ChatTranscript({
  messages,
  draft,
}: {
  messages: { id: string | number; role: string; content: string }[];
  draft?: string;
}) {
  return (
    <ol aria-label="Messages" className="space-y-3">
      {messages.map((m) => (
        <li
          key={m.id}
          className={`max-w-[90%] rounded-xl p-3 text-sm whitespace-pre-wrap ${m.role === "user" ? "ml-auto bg-primary text-primary-foreground" : "bg-muted"}`}
        >
          {m.content}
        </li>
      ))}
      {draft && (
        <li
          className="max-w-[90%] rounded-xl bg-muted p-3 text-sm whitespace-pre-wrap"
          aria-live="polite"
        >
          {draft}
        </li>
      )}
    </ol>
  );
}
export function Composer({
  disabled,
  send,
}: {
  disabled: boolean;
  send: (text: string) => Promise<void>;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim() || disabled || busy) return;
    setBusy(true);
    setError("");
    try {
      await send(text.trim());
      setText("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={(e) => void submit(e)} className="space-y-2">
      <Textarea
        aria-label="Message"
        placeholder="Ask the assistant…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={4000}
      />
      <Button disabled={disabled || busy || !text.trim()}>Send</Button>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}

/** Review is application-owned: this component only edits a value and calls explicit callbacks. */
export function ReviewCard({
  title,
  before,
  value,
  accept,
  reject,
  disabled = false,
}: {
  title: string;
  before?: unknown;
  value: unknown;
  accept: (value: unknown) => Promise<void>;
  reject: () => Promise<void>;
  disabled?: boolean;
}) {
  const [edited, setEdited] = useState(() =>
    typeof value === "string" ? value : JSON.stringify(value, null, 2),
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function decide(accepted: boolean) {
    setBusy(true);
    setError("");
    try {
      if (accepted) await accept(typeof value === "string" ? edited : JSON.parse(edited));
      else await reject();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label={title} className="space-y-3 rounded-xl border bg-card p-4">
      <h3 className="font-medium">{title}</h3>
      {before !== undefined && (
        <div className="rounded bg-muted p-3">
          <p className="mb-1 text-xs text-muted-foreground">Current value</p>
          <StructuredResult value={before} />
        </div>
      )}
      <StructuredResult value={value} />
      <details>
        <summary className="cursor-pointer text-sm">Edit before accepting</summary>
        <Textarea
          aria-label={`Edit ${title}`}
          className="mt-2 min-h-32 font-mono text-sm"
          value={edited}
          onChange={(e) => setEdited(e.target.value)}
        />
      </details>
      <div className="flex gap-2">
        <Button disabled={disabled || busy} onClick={() => void decide(true)}>
          Accept
        </Button>
        <Button variant="outline" disabled={disabled || busy} onClick={() => void decide(false)}>
          Reject
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </section>
  );
}

export function Citations({ items }: { items: { id: string; label: string; href: string }[] }) {
  return (
    <ul aria-label="Sources" className="space-y-1 text-xs">
      {items.map((item) => (
        <li key={item.id}>
          <a href={item.href} className="text-primary underline">
            {item.label}
          </a>
        </li>
      ))}
    </ul>
  );
}
export function ToolActivity({ events }: { events: Interaction["events"] }) {
  const tools = events.filter((event) => event.type === "TOOL_CALL_START");
  if (!tools.length) return null;
  return (
    <ul aria-label="Assistant actions" className="text-xs text-muted-foreground">
      {tools.map((event) => (
        <li key={String(event.toolCallId)}>
          Assistant action: {String(event.toolCallName).replaceAll("_", " ")}
        </li>
      ))}
    </ul>
  );
}
