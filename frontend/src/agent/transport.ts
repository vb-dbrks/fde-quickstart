import { EventSchema } from "@ag-ui/core/schemas";
import { AbstractAgent } from "@ag-ui/client";
import { type BaseEvent } from "@ag-ui/core";
import { Observable } from "rxjs";

export class RequestError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(new Request(`${window.location.origin}/api${path}`, init));
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new RequestError(
      response.status,
      typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}

export function post<T>(
  path: string,
  body: unknown,
  key: string = crypto.randomUUID(),
): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": key },
    body: JSON.stringify(body),
  });
}

export type Envelope = { sequence: number; event: BaseEvent };
type Batch = { events: Envelope[]; cursor: number; terminal: boolean };

/** App cursor transport, not the standard POST/SSE binding. Attaches without resubmitting work. */
export class DurableAgent extends AbstractAgent {
  readonly appRunId: string;
  constructor(appRunId: string) {
    super({ agentId: "application", threadId: appRunId });
    this.appRunId = appRunId;
  }

  run(): Observable<BaseEvent> {
    return new Observable((subscriber) => {
      const controller = new AbortController();
      let cursor = 0;
      let terminal = false;
      const deliver = (item: Envelope) => {
        if (item.sequence <= cursor) return;
        if (item.sequence !== cursor + 1) throw new Error("Missing interaction event");
        const event = EventSchema.parse(item.event);
        subscriber.next(event);
        cursor = item.sequence;
        terminal = event.type === "RUN_FINISHED" || event.type === "RUN_ERROR";
      };
      const path = () => `/runs/${encodeURIComponent(this.appRunId)}/events?after=${cursor}`;
      const stream = async () => {
        const streamController = new AbortController();
        const stop = () => streamController.abort();
        controller.signal.addEventListener("abort", stop, { once: true });
        let watchdog = setTimeout(stop, 15000);
        try {
          const response = await fetch(
            new Request(`${window.location.origin}/api${path()}`, {
              headers: { Accept: "text/event-stream" },
              signal: streamController.signal,
            }),
          );
          if (!response.ok) throw new RequestError(response.status, "Cannot read this interaction");
          const reader = response.body?.getReader();
          if (!reader) throw new Error("Streaming unavailable");
          const decoder = new TextDecoder();
          let pending = "";
          try {
            while (!terminal) {
              const { done, value } = await reader.read();
              if (done) break;
              clearTimeout(watchdog);
              watchdog = setTimeout(stop, 15000);
              pending += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
              let boundary: number;
              while ((boundary = pending.indexOf("\n\n")) >= 0) {
                const frame = pending.slice(0, boundary);
                pending = pending.slice(boundary + 2);
                if (frame.includes("event: access-denied"))
                  throw new RequestError(403, "Access to this interaction changed");
                if (frame.includes("event: complete")) {
                  terminal = true;
                  break;
                }
                const data = frame
                  .split("\n")
                  .filter((line) => line.startsWith("data:"))
                  .map((line) => line.slice(5).trimStart())
                  .join("\n");
                if (data) deliver(JSON.parse(data) as Envelope);
              }
            }
          } finally {
            await reader.cancel();
          }
        } finally {
          clearTimeout(watchdog);
          controller.signal.removeEventListener("abort", stop);
          streamController.abort();
        }
      };
      const follow = async () => {
        try {
          await stream();
        } catch (error) {
          if (controller.signal.aborted) return;
          if (error instanceof RequestError && [401, 403, 404].includes(error.status)) throw error;
        }
        let failures = 0;
        while (!terminal && !controller.signal.aborted) {
          try {
            const batch = await request<Batch>(path(), { signal: controller.signal });
            batch.events.forEach(deliver);
            terminal = batch.terminal;
            failures = 0;
          } catch (error) {
            if (controller.signal.aborted) return;
            if (error instanceof RequestError && [401, 403, 404].includes(error.status))
              throw error;
            if (++failures >= 5) throw error;
          }
          if (!terminal)
            await new Promise<void>((resolve) => {
              const finish = () => {
                clearTimeout(timer);
                controller.signal.removeEventListener("abort", finish);
                resolve();
              };
              const timer = setTimeout(finish, 1000);
              controller.signal.addEventListener("abort", finish, { once: true });
            });
        }
        if (!controller.signal.aborted) subscriber.complete();
      };
      void follow().catch((error: unknown) => subscriber.error(error));
      return () => controller.abort();
    });
  }
}
