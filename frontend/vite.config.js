import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendTarget = process.env.RWKV_ECRA_FRONTEND_API || "http://127.0.0.1:8787";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/frontend-api": {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
});
