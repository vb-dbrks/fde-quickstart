import { Link } from "react-router";
import { examples, useExamples } from "@/examples/registry";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function HomePage() {
  const enabled = useExamples();
  return (
    <>
      <PageHeader
        title="Build your agentic application"
        description="Start with a working pattern. Adapt its agent, schemas and UI to your project."
      />
      {enabled.error && <p role="alert">{enabled.error.message}</p>}
      <div className="grid gap-5 md:grid-cols-3">
        {examples
          .filter((e) => enabled.data?.includes(e.id))
          .map(({ id, title, path, description, icon: Icon }) => (
            <Card key={id}>
              <CardHeader>
                <Icon className="mb-4 size-7 text-primary" />
                <CardTitle>{title}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-5">
                <p className="text-sm text-muted-foreground">{description}</p>
                <Button asChild variant="outline">
                  <Link to={`/${path}`}>Open {title.toLowerCase()}</Link>
                </Button>
              </CardContent>
            </Card>
          ))}
      </div>
      <p className="text-sm text-muted-foreground">
        All examples share the same authentication, agent interactions, persistence and feedback
        foundation. Locally, the fake agent works without model credentials.
      </p>
    </>
  );
}
