import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Verification checklist:
    // - backend running on http://localhost:8000
    // - frontend running on http://localhost:5173
    // - click generate and confirm /api/* requests are proxied to the backend
    // - POST /api/generate-resume returns a real backend response
    // - SSE /api/pipeline-runs/{run_id}/events connects without Vite 404s
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
