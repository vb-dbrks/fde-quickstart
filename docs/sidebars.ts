import type { SidebarsConfig } from "@docusaurus/plugin-content-docs";

const sidebars: SidebarsConfig = {
  docs: [
    { type: "doc", id: "index", label: "Overview" },
    {
      type: "category",
      label: "Architecture",
      collapsed: false,
      items: [
        "architecture/layers",
        "architecture/data-model",
        "architecture/run-lifecycle",
        {
          type: "category",
          label: "Decision records",
          items: [
            "architecture/adr/0001-single-app-in-process-agent",
            "architecture/adr/0002-lakebase-system-of-record",
            "architecture/adr/0003-async-submit-poll",
            "architecture/adr/0004-stateless-agent-contract",
            "architecture/adr/0005-golden-record-and-versioning",
            "architecture/adr/0006-fake-agent",
            "architecture/adr/0007-permissions-and-document-access",
            "architecture/adr/0008-notifications-by-polling",
            "architecture/adr/0009-migrations-at-startup",
            "architecture/adr/0010-user-feedback-on-traces",
            "architecture/adr/0011-generic-ag-ui-interactions",
          ],
        },
      ],
    },
    {
      type: "category",
      label: "Guides",
      collapsed: false,
      items: [
        "guides/getting-started",
        "guides/agentic-applications",
        "guides/ag-ui-verification",
        "guides/agent-contract",
        "guides/adding-a-run-kind",
        "guides/adding-a-document-type",
        "guides/fake-agent",
        "guides/splitting-the-agent",
        "guides/permissions",
        "guides/migrations",
        "guides/deploy-and-ci",
        "guides/evals",
        "guides/user-feedback",
      ],
    },
  ],
};

export default sidebars;
