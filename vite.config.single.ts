// Single-file build: inlines all JS/CSS into one self-contained index.html for
// hosting the web app as a standalone page (e.g. a shareable artifact). The
// normal multi-file build (vite.config.ts) is still what the web/desktop use.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

export default defineConfig({
  plugins: [react(), viteSingleFile()],
  base: "./",
  build: {
    target: "es2020",
    outDir: "dist-single",
    cssCodeSplit: false,
    assetsInlineLimit: 100000000,
    reportCompressedSize: false,
    rollupOptions: { output: { inlineDynamicImports: true } },
  },
});
