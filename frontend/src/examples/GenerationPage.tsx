import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { request, post } from "@/agent/transport";
import { useInteraction } from "@/agent/AgentProvider";
import { ReviewCard, StructuredResult, RunActivity } from "@/agent/components";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { usePermissions } from "@/lib/permissions";
import { useRuns, runKey } from "@/agent/queries";
import type { Run } from "@/agent/types";

export function GenerationPage() {
  const [params, setParams] = useSearchParams();
  const runId = params.get("run");
  const [topic, setTopic] = useState("");
  const [audience, setAudience] = useState("");
  const [constraints, setConstraints] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const interaction = useInteraction(runId);
  const cache = useQueryClient();
  const { can } = usePermissions();
  const runs = useRuns("generation");
  const review = useQuery({
    queryKey: ["generation-review", runId],
    queryFn: () =>
      request<{ status: string; value?: Record<string, unknown> }>(`/runs/${runId}/review`),
    enabled: !!runId,
  });
  useEffect(() => {
    if (interaction.finished) {
      void cache.invalidateQueries({ queryKey: ["generation-review", runId] });
      void cache.invalidateQueries({ queryKey: runKey("generation") });
    }
  }, [interaction.finished, runId, cache]);
  async function generate(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const run = await post<Run>("/runs", {
        agent_id: "generation",
        input: { topic, audience: audience || "General audience", constraints },
      });
      setParams({ run: run.id });
      void cache.invalidateQueries({ queryKey: runKey("generation") });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }
  async function decide(decision: string, value?: unknown) {
    await post(`/runs/${runId}/review`, { decision, ...(value === undefined ? {} : { value }) });
    await cache.invalidateQueries({ queryKey: ["generation-review", runId] });
  }
  return (
    <>
      <PageHeader
        title="Generate"
        description="Turn an idea into structured content, then review it before saving."
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <form onSubmit={(e) => void generate(e)} className="space-y-4 rounded-xl border p-5">
          <label className="block space-y-1">
            <span>Topic</span>
            <Input
              required
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              maxLength={2000}
            />
          </label>
          <label className="block space-y-1">
            <span>Audience</span>
            <Input
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              maxLength={2000}
            />
          </label>
          <label className="block space-y-1">
            <span>Constraints</span>
            <Textarea
              value={constraints}
              onChange={(e) => setConstraints(e.target.value)}
              maxLength={4000}
            />
          </label>
          <Button disabled={submitting || !can("agents:run")}>Generate draft</Button>
          {error && <p role="alert">{error}</p>}
        </form>
        <div className="space-y-4">
          {runId && <RunActivity interaction={interaction} />}
          {runId && !interaction.finished && (
            <div className="rounded-xl border border-dashed p-4">
              <p className="mb-3 text-sm text-muted-foreground">Draft preview · not saved</p>
              <StructuredResult value={interaction.state.preview} />
            </div>
          )}
          {review.data?.status === "pending" && (
            <ReviewCard
              key={runId}
              title="Review generated content"
              value={review.data.value}
              accept={(value) => decide("accepted", value)}
              reject={() => decide("rejected")}
            />
          )}
          {review.data && ["accepted", "rejected"].includes(review.data.status) && (
            <div className="space-y-3 rounded-xl border p-4">
              <p className="text-sm font-medium">
                {review.data.status === "accepted" ? "Saved result" : "Draft rejected"}
              </p>
              <StructuredResult value={review.data.value} />
            </div>
          )}
          <details>
            <summary>Previous generations</summary>
            <ul>
              {runs.data?.map((r) => (
                <li key={r.id}>
                  <Button variant="ghost" onClick={() => setParams({ run: r.id })}>
                    {String(r.result?.title ?? "Generation")} · {r.status}
                  </Button>
                </li>
              ))}
            </ul>
          </details>
        </div>
      </div>
    </>
  );
}
