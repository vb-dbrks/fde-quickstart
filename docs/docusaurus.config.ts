// Documentation site: `make docs` serves it on :3000, `make docs-build` builds it (CI fails on broken
// links). Pages are Markdown in content/; the sidebar is sidebars.ts.
import type * as Preset from "@docusaurus/preset-classic";
import type { Config } from "@docusaurus/types";
import { themes as prismThemes } from "prism-react-renderer";

const config: Config = {
  title: "Quickstart App",
  tagline: "A Databricks App with a stateless agent and Lakebase as the system of record",
  url: "http://localhost",
  baseUrl: "/",
  onBrokenLinks: "throw",
  onBrokenAnchors: "throw",
  markdown: {
    mermaid: true,
    hooks: { onBrokenMarkdownLinks: "throw" },
  },
  themes: ["@docusaurus/theme-mermaid"],
  presets: [
    [
      "classic",
      {
        docs: {
          path: "content",
          routeBasePath: "/",
          sidebarPath: "./sidebars.ts",
          // Keep "0001-" in decision record ids and URLs.
          numberPrefixParser: false,
        },
        blog: false,
        pages: false,
        theme: { customCss: "./src/css/custom.css" },
      } satisfies Preset.Options,
    ],
  ],
  themeConfig: {
    navbar: {
      title: "Quickstart App",
      items: [
        { type: "docSidebar", sidebarId: "docs", position: "left", label: "Docs" },
      ],
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ["bash", "json", "yaml", "python"],
    },
    mermaid: { theme: { light: "neutral", dark: "dark" } },
  } satisfies Preset.ThemeConfig,
};

export default config;
