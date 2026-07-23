/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: false,
  },
  // Relative-path build so the same bundle works when loaded from the filesystem
  // (Electron desktop shell) as well as from a web host on any sub-path.
  base: "./",
  build: {
    target: "es2020",
    outDir: "dist",
    rollupOptions: {
      // Multi-page: marketing landing at "/" and the app at "/app/".
      input: {
        main: "index.html",
        app: "app/index.html",
      },
    },
  },
  test: {
    globals: true,
    environment: "node",
    include: ["src/**/*.{test,spec}.ts"],
  },
});
