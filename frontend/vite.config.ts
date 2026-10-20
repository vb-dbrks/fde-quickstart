import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  build: {
    // FastAPI serves the built app (backend/app/spa.py); the folder is uploaded on deploy.
    outDir: "../backend/app/static",
    emptyOutDir: true,
    // React, React Router, Radix and TanStack Query come to ~540 kB minified (~170 kB gzipped).
    // As the app grows, load pages on demand with route `lazy()` instead of raising this further.
    chunkSizeWarningLimit: 700,
  },
  server: {
    port: 5173,
    // `make dev` runs the backend on :8000.
    proxy: { "/api": "http://localhost:8000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
