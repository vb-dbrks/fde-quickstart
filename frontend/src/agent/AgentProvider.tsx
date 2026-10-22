import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import type { BaseEvent, Message } from "@ag-ui/core";
import { DurableAgent } from "@/agent/transport";

export type Interaction = {
  state: Record<string, unknown>;
  messages: readonly Readonly<Message>[];
  events: BaseEvent[];
  toolEvents: BaseEvent[];
  finished: boolean;
  error?: string;
};
const EMPTY: Interaction = { state: {}, messages: [], events: [], toolEvents: [], finished: false };
class RunStore {
  snapshot: Interaction = EMPTY;
  listeners = new Set<() => void>();
  private agent?: DurableAgent;
  readonly id: string;
  constructor(id: string) {
    this.id = id;
  }
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  read = () => this.snapshot;
  update(change: Partial<Interaction>) {
    this.snapshot = { ...this.snapshot, ...change };
    this.listeners.forEach((listener) => listener());
  }
  start() {
    if (this.agent || this.snapshot.finished) return;
    const agent = new DurableAgent(this.id);
    this.agent = agent;
    const update = (change: Partial<Interaction>) => {
      if (this.agent === agent) this.update(change);
    };
    void agent
      .runAgent(
        { runId: this.id },
        {
          onEvent: ({ event }) => {
            update({
              events: [...this.snapshot.events.slice(-199), event],
              toolEvents: event.type.startsWith("TOOL_CALL_")
                ? [...this.snapshot.toolEvents, event]
                : this.snapshot.toolEvents,
            });
          },
          onStateChanged: ({ state }) => {
            update({ state: state as Record<string, unknown> });
          },
          onMessagesChanged: ({ messages }) => {
            update({ messages });
          },
          onRunErrorEvent: ({ event }) => {
            update({ error: event.message, finished: true });
          },
          onRunFinalized: () => {
            update({ finished: true });
          },
        },
      )
      .catch((error: Error) => {
        update({ error: error.message, finished: true });
      });
  }
  stop() {
    const previous = this.agent;
    this.agent = undefined;
    if (!this.snapshot.finished) this.update(EMPTY);
    previous?.abortRun();
  }
}
const Context = createContext<Map<string, RunStore> | null>(null);
export function AgentProvider({ children }: { children: ReactNode }) {
  const stores = useMemo(() => new Map<string, RunStore>(), []);
  useEffect(
    () => () => {
      stores.forEach((store) => store.stop());
    },
    [stores],
  );
  return <Context.Provider value={stores}>{children}</Context.Provider>;
}
export function useInteraction(runId?: string | null): Interaction {
  const stores = useContext(Context);
  const store = useMemo(() => {
    if (!runId || !stores) return undefined;
    let found = stores.get(runId);
    if (!found) {
      found = new RunStore(runId);
      stores.set(runId, found);
    }
    return found;
  }, [runId, stores]);
  useEffect(() => {
    store?.start();
  }, [store]);
  return useSyncExternalStore(store?.subscribe ?? (() => () => {}), store?.read ?? (() => EMPTY));
}
