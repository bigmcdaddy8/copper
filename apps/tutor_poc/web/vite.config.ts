import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies the API to a running `uv run tutor_poc serve` (port 8765).
export default defineConfig({
  plugins: [react()],
  // The company logo is imported from the repo's docs/ (outside this project), so the dev server may read it.
  server: { proxy: { "/api": "http://127.0.0.1:8765" }, fs: { allow: [".", "../../../docs/company_logo.png"] } },
  test: { environment: "node" },
} as any);
