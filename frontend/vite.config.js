import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendTarget = process.env.RWKV_ECRA_FRONTEND_API || "http://127.0.0.1:8787";
const srcDir = fileURLToPath(new URL("./src", import.meta.url));

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": srcDir,
    },
  },
  server: {
    proxy: {
      "/frontend-api": {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
});
