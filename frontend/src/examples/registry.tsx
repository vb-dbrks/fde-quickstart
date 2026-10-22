import { useQuery } from "@tanstack/react-query";
import { FileText, MessageSquare, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { request } from "@/agent/transport";
import { ChatPage } from "@/examples/ChatPage";
import { GenerationPage } from "@/examples/GenerationPage";
import { DocumentPage } from "@/pages/DocumentPage";
import { DocumentsPage } from "@/pages/DocumentsPage";

/** Explicit composition: removing a registration removes its navigation, routes and example card. */
export const examples = [
  {
    id: "chat",
    title: "Chat",
    path: "chat",
    icon: MessageSquare,
    description: "Streaming conversations, optional context and feedback.",
    routes: [{ path: "chat", element: <ChatPage /> }],
  },
  {
    id: "generation",
    title: "Generation",
    path: "generation",
    icon: Sparkles,
    description: "Structured input and output, editable drafts and explicit acceptance.",
    routes: [{ path: "generation", element: <GenerationPage /> }],
  },
  {
    id: "documents",
    title: "Documents",
    path: "documents",
    icon: FileText,
    description: "Records, source citations, reviewable changes and assistant UI actions.",
    routes: [
      { path: "documents", element: <DocumentsPage /> },
      { path: "documents/:documentId", element: <DocumentPage /> },
    ],
  },
];
export function useExamples() {
  return useQuery({
    queryKey: ["enabled-examples"],
    queryFn: () => request<string[]>("/examples"),
    staleTime: 60000,
  });
}
export function ExampleRoute({ id, children }: { id: string; children: ReactNode }) {
  const enabled = useExamples();
  if (enabled.isPending) return <p>Loading…</p>;
  if (enabled.isError) return <p role="alert">{enabled.error.message}</p>;
  return enabled.data.includes(id) ? children : <p>This example is not enabled.</p>;
}
