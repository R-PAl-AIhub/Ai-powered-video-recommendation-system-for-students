import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  // "/" when the backend serves the app; the repository path for the GitHub Pages demo.
  // (Read through globalThis so the type-check needs no Node type definitions.)
  base:
    (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env
      .PAGES_BASE ?? "/",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // The API keeps the browser's Host header, so its same-origin check passes in dev.
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: {
    target: "es2022",
    sourcemap: false,
    rollupOptions: {
      output: {
        // The 3D scene is the heaviest part of the bundle and only the landing page
        // needs it, so it gets its own chunks, loaded on demand.
        manualChunks: {
          three: ["three"],
          r3f: ["@react-three/fiber", "@react-three/drei"],
          motion: ["motion"],
        },
      },
    },
  },
});
