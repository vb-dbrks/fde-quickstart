import { Bot, MessageSquarePlus, Send } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/EmptyState";
import { RatingControl } from "@/components/documents/RatingControl";
import { RunProgress } from "@/components/documents/RunProgress";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { keyed, type AgentRun, type Message } from "@/lib/api";
import { isTerminal, useAgentRun } from "@/lib/agentRuns";
import { formatDateTime } from "@/lib/format";
import {
  useCreateThread,
  useMessages,
  useRateAnswer,
  useStartAgentRun,
  useThreads,
} from "@/lib/queries";
import { cn } from "@/lib/utils";

/**
 * Chat about a document. Each message is an ``assistant_turn`` run: the app stores the thread in
 * Lakebase and sends the agent the document plus recent history every time, so the agent keeps
 * no conversation state of its own.
 */
export function AssistantPanel({
  documentId,
  canChat,
  activeRun,
}: {
  documentId: string;
  canChat: boolean;
  /** An assistant turn still in progress (after a reload). */
  activeRun?: AgentRun;
}) {
  const threads = useThreads(documentId);
  const [chosen, setChosen] = useState<string | undefined>(activeRun?.thread_id ?? undefined);
  const threadId = chosen ?? threads.data?.[0]?.id;
  // Kept here rather than in Conversation, so starting the first thread doesn't lose the run.
  const [runId, setRunId] = useState(activeRun?.id);
  const createThread = useCreateThread(documentId);

  if (threads.isPending) return <Skeleton className="h-40 w-full" />;
  if (!canChat) {
    return (
      <EmptyState
        icon={Bot}
        title="You can't use the assistant yet"
        description="Ask an admin for the editor role."
      />
    );
  }

  function newThread() {
    createThread.mutate(undefined, {
      onSuccess: (thread) => setChosen(thread.id),
      onError: (error) => toast.error(error.message),
    });
  }

  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          {threads.data && threads.data.length > 0 ? (
            <NativeSelect
              aria-label="Conversation"
              value={threadId}
              onChange={(event) => setChosen(event.target.value)}
            >
              {threads.data.map((thread) => (
                <option key={thread.id} value={thread.id}>
                  {thread.title} · {formatDateTime(thread.created_at)}
                </option>
              ))}
            </NativeSelect>
          ) : (
            <p className="text-sm text-muted-foreground">
              Ask about this document. Conversations are private to you.
            </p>
          )}
          <Button variant="outline" size="sm" onClick={newThread} disabled={createThread.isPending}>
            <MessageSquarePlus aria-hidden /> New conversation
          </Button>
        </div>
        <Conversation
          documentId={documentId}
          threadId={threadId}
          runId={runId}
          onRunStarted={setRunId}
          onThreadCreated={setChosen}
        />
      </CardContent>
    </Card>
  );
}

function Conversation({
  documentId,
  threadId,
  runId,
  onRunStarted,
  onThreadCreated,
}: {
  documentId: string;
  threadId: string | undefined;
  runId: string | undefined;
  onRunStarted: (runId: string) => void;
  onThreadCreated: (threadId: string) => void;
}) {
  const [message, setMessage] = useState("");
  const messages = useMessages(threadId);
  const createThread = useCreateThread(documentId);
  const start = useStartAgentRun(documentId);
  const tracked = useAgentRun(runId, {
    onSettled: (settled) => {
      if (settled.status === "failed") toast.error("The assistant couldn't answer");
    },
  }).data;
  // Only show the run in the conversation it belongs to.
  const run = tracked && tracked.thread_id === threadId ? tracked : undefined;
  const thinking =
    createThread.isPending || start.isPending || (run !== undefined && !isTerminal(run.status));
  // Set synchronously, so a second Enter before React re-renders can't start a second thread.
  const sending = useRef(false);

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = message.trim();
    if (!text || thinking || sending.current) return;
    sending.current = true;
    try {
      const thread = threadId ?? (await createThread.mutateAsync(undefined)).id;
      if (!threadId) onThreadCreated(thread);
      const started = await start.mutateAsync(
        keyed({ run_kind: "assistant_turn", thread_id: thread, message: text }),
      );
      setMessage("");
      onRunStarted(started.id);
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      sending.current = false;
    }
  }

  return (
    <div className="space-y-4">
      <ol aria-label="Messages" aria-live="polite" className="space-y-3">
        {messages.data?.map((item) => (
          <li
            key={item.id}
            className={cn(
              "max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap",
              item.role === "user" ? "ml-auto bg-primary text-primary-foreground" : "bg-muted",
            )}
          >
            {item.content}
            {item.role === "assistant" && item.agent_run_id && threadId && (
              <div className="-mr-2 -mb-1 flex justify-end">
                <AnswerRating threadId={threadId} message={item} />
              </div>
            )}
          </li>
        ))}
        {run && !isTerminal(run.status) && (
          <li className="max-w-[85%] rounded-lg bg-muted/50 px-3 py-2">
            <RunProgress run={run} />
          </li>
        )}
        {run?.status === "failed" && (
          <li className="max-w-[85%] rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {run.error_message ?? "The assistant couldn't answer."}
          </li>
        )}
      </ol>
      <form onSubmit={send} className="flex items-end gap-2">
        <Textarea
          aria-label="Message"
          placeholder="Ask about this document…"
          value={message}
          maxLength={4_000}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) void send(event);
          }}
        />
        <Button type="submit" size="icon" aria-label="Send" disabled={thinking}>
          <Send aria-hidden />
        </Button>
      </form>
      <p className="text-xs text-muted-foreground">
        The app sends the agent this document and the recent conversation with every message.
      </p>
    </div>
  );
}

function AnswerRating({ threadId, message }: { threadId: string; message: Message }) {
  const rate = useRateAnswer(threadId, message.id);
  return (
    <RatingControl
      label="this answer"
      current={message.my_rating}
      rate={(rating, options) =>
        rate.mutate(rating, { ...options, onError: (error) => toast.error(error.message) })
      }
    />
  );
}
