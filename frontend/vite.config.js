import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import fs from "node:fs";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendTarget = process.env.RWKV_ECRA_FRONTEND_API || "http://127.0.0.1:8787";
const srcDir = fileURLToPath(new URL("./src", import.meta.url));

// 定位本地的 global_token_usage.json 文件
const frontendDir = dirname(fileURLToPath(import.meta.url));
const tokenFilePath = resolve(frontendDir, "../data/output/global_token_usage.json");

export default defineConfig({
  plugins: [
    react(), 
    tailwindcss(),
    // ✨ 核心修复：在这个拦截器中直接读取本地 JSON 给前端，不让它流到后端去
    {
      name: 'serve-token-usage',
      configureServer(server) {
        server.middlewares.use('/frontend-api/tokens', (req, res) => {
          res.setHeader('Content-Type', 'application/json');
          try {
            if (fs.existsSync(tokenFilePath)) {
              const data = fs.readFileSync(tokenFilePath, 'utf-8');
              res.end(JSON.stringify({ code: 200, data: JSON.parse(data) }));
            } else {
              res.end(JSON.stringify({ code: 200, data: { tasks: {} } }));
            }
          } catch (e) {
            res.statusCode = 500;
            res.end(JSON.stringify({ code: 500, message: String(e) }));
          }
        });
      }
    }
  ],
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