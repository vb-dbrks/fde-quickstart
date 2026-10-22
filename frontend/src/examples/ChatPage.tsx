import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { post } from "@/agent/transport";
import { useInteraction } from "@/agent/AgentProvider";
import { ChatTranscript, Composer, RunActivity } from "@/agent/components";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { usePermissions } from "@/lib/permissions";

import { useSessions, useSessionMessages, useRuns, sessionKeys, runKey } from "@/agent/queries";
import type { Run } from "@/agent/types";
type Session = { id: string; title: string };

export function ChatPage() {
  const [params, setParams] = useSearchParams();
  const sessionId = params.get("session");
  const [context, setContext] = useState("");
  const [started, setStarted] = useState<Run>();
  const cache = useQueryClient();
  const { can } = usePermissions();
  const sessions = useSessions("chat");
  const messages = useSessionMessages(sessionId);
  const runs = useRuns("chat", sessionId, !!sessionId);
  const run =
    started?.thread_id === sessionId
      ? started
      : runs.data?.find((r) => !["succeeded", "failed"].includes(r.status));
  const interaction = useInteraction(run?.id);
  useEffect(() => {
    if (interaction.finished) {
      void cache.invalidateQueries({ queryKey: sessionKeys.messages(sessionId) });
      void cache.invalidateQueries({ queryKey: runKey("chat", sessionId) });
    }
  }, [interaction.finished, sessionId, cache]);
  const busy = !!run && !interaction.finished;
  const preview = interaction.state.preview as { content?: string } | undefined;
  return (
    <>
      <PageHeader title="Chat" description="A conversational assistant with optional context." />
      <div className="grid gap-6 md:grid-cols-[200px_1fr]">
        <aside className="space-y-3">
          <Button
            variant="outline"
            onClick={() => {
              setParams({});
              setStarted(undefined);
            }}
          >
            New conversation
          </Button>
          <ul className="space-y-1">
            {sessions.data?.map((s) => (
              <li key={s.id}>
                <Button
                  className="w-full justify-start truncate"
                  variant={s.id === sessionId ? "secondary" : "ghost"}
                  onClick={() => {
                    setParams({ session: s.id });
                    setStarted(undefined);
                  }}
                >
                  {s.title}
                </Button>
              </li>
            ))}
          </ul>
        </aside>
        <section className="space-y-4 rounded-xl border p-5">
          {messages.error && <p role="alert">{messages.error.message}</p>}
          <ChatTranscript
            messages={messages.data ?? []}
            draft={busy ? preview?.content : undefined}
          />
          {run && <RunActivity interaction={interaction} />}
          <details>
            <summary className="text-sm text-muted-foreground">
              Context for this conversation
            </summary>
            <Textarea
              className="mt-2"
              aria-label="Assistant context"
              value={context}
              onChange={(e) => setContext(e.target.value)}
              maxLength={12000}
            />
          </details>
          <Composer
            disabled={busy || !can("agents:run")}
            send={async (message) => {
              let id = sessionId;
              if (!id) {
                const session = await post<Session>("/sessions", {
                  agent_id: "chat",
                  title: message.slice(0, 80),
                });
                id = session.id;
                setParams({ session: id });
                void cache.invalidateQueries({ queryKey: ["sessions", "chat"] });
              }
              const result = await post<Run>("/runs", {
                agent_id: "chat",
                session_id: id,
                input: { message, context },
              });
              setStarted(result);
              void cache.invalidateQueries({ queryKey: sessionKeys.messages(id) });
            }}
          />
          {!can("agents:run") && (
            <p className="text-sm text-muted-foreground">
              Ask an admin for the editor role to use the assistant.
            </p>
          )}
          {messages.data
            ?.filter((m) => m.role === "assistant" && m.agent_run_id)
            .slice(-1)
            .map((m) => (
              <AnswerFeedback key={m.id} runId={m.agent_run_id!} />
            ))}
        </section>
      </div>
    </>
  );
}
function AnswerFeedback({ runId }: { runId: string }) {
  const [status, setStatus] = useState("");
  async function rate(rating: boolean) {
    try {
      await post(`/runs/${runId}/feedback`, { rating });
      setStatus("Feedback saved");
    } catch (e) {
      setStatus((e as Error).message);
    }
  }
  return (
    <div className="flex items-center gap-2 text-sm">
      <span>Was this helpful?</span>
      <Button size="sm" variant="ghost" onClick={() => void rate(true)}>
        Yes
      </Button>
      <Button size="sm" variant="ghost" onClick={() => void rate(false)}>
        No
      </Button>
      <span role="status">{status}</span>
    </div>
  );
}
