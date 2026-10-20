import { Bot, Send, ShieldX } from "lucide-react";
import { useState, type FormEvent } from "react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { QueryError } from "@/components/QueryError";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { usePermissions } from "@/lib/permissions";
import { useAgents, useInvokeAgent } from "@/lib/queries";
import { cn } from "@/lib/utils";

const AGENT = "assistant";

type Turn = { role: "user" | "assistant" | "error"; text: string };

export function AssistantPage() {
  const agents = useAgents();
  const { can } = usePermissions();
  const agent = agents.data?.find((candidate) => candidate.name === AGENT);

  let content;
  if (agents.isPending) {
    content = <Skeleton className="h-40 w-full" />;
  } else if (agents.isError) {
    content = <QueryError error={agents.error} onRetry={() => agents.refetch()} />;
  } else if (!agent?.configured) {
    content = (
      <EmptyState
        icon={Bot}
        title="The assistant isn't set up"
        description="Set the llm_endpoint bundle variable to a Model Serving endpoint and redeploy."
      />
    );
  } else if (!can("agents:invoke")) {
    content = (
      <EmptyState
        icon={ShieldX}
        title="You can't use the assistant yet"
        description="Ask an admin for the editor role."
      />
    );
  } else {
    content = <Conversation />;
  }

  return (
    <>
      <PageHeader
        title="Assistant"
        description={agent?.description ?? "An agent that works with your notes."}
      />
      {content}
    </>
  );
}

function Conversation() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [message, setMessage] = useState("");
  const invoke = useInvokeAgent(AGENT);

  function send(event: FormEvent) {
    event.preventDefault();
    const text = message.trim();
    if (!text) return;
    setTurns((previous) => [...previous, { role: "user", text }]);
    setMessage("");
    invoke.mutate(text, {
      onSuccess: (reply) =>
        setTurns((previous) => [...previous, { role: "assistant", text: reply.output }]),
      onError: (error) =>
        setTurns((previous) => [...previous, { role: "error", text: error.message }]),
    });
  }

  return (
    <Card>
      <CardContent className="space-y-4">
        <ol aria-live="polite" className="space-y-3">
          {turns.map((turn, index) => (
            <li
              key={index}
              className={cn(
                "max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap",
                turn.role === "user" && "ml-auto bg-primary text-primary-foreground",
                turn.role === "assistant" && "bg-muted",
                turn.role === "error" && "bg-destructive/10 text-destructive",
              )}
            >
              {turn.text}
            </li>
          ))}
          {invoke.isPending && <li className="text-sm text-muted-foreground">Thinking…</li>}
        </ol>
        <form onSubmit={send} className="flex items-end gap-2">
          <Textarea
            aria-label="Message"
            placeholder="Ask about your notes, or ask me to write one…"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) send(event);
            }}
          />
          <Button type="submit" size="icon" aria-label="Send" disabled={invoke.isPending}>
            <Send aria-hidden />
          </Button>
        </form>
        <p className="text-xs text-muted-foreground">
          Each message is answered on its own; the assistant does not remember earlier turns.
        </p>
      </CardContent>
    </Card>
  );
}
