/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Tauri expects a fixed port and does not fall back to another one.
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: false,
  },
  // Produce a relative-path build so the same bundle works when loaded from
  // the filesystem inside the Tauri desktop shell as well as from a web host.
  base: "./",
  build: {
    target: "es2020",
    outDir: "dist",
  },
  test: {
    globals: true,
    environment: "node",
    include: ["src/**/*.{test,spec}.ts"],
  },
});
