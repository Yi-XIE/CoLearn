import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.COLEARN_API_URL ?? "http://127.0.0.1:8001";

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    optimizeDeps: {
      // Radix dialog was introduced mid-session for the mobile sidebar sheet.
      // When Vite re-optimizes it on a running dev server, the browser can race
      // and request stale chunk paths from `.vite/deps`. Excluding it keeps dev
      // reloads stable instead of rewriting those chunk filenames under us.
      exclude: ["@radix-ui/react-dialog"],
    },
    build: {
      outDir: path.resolve(__dirname, "../.colearn/webui/dist"),
      emptyOutDir: true,
      sourcemap: false,
    },
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      hmr: {
        host: "127.0.0.1",
        port: 5174,
      },
      proxy: {
        // Single gateway: all traffic goes to CoLearn FastAPI which proxies
        // /webui, /auth, and / (WS) to nanobot internally.
        "/webui": { target: apiTarget, changeOrigin: true },
        "/auth": { target: apiTarget, changeOrigin: true },
        "/api": { target: apiTarget, changeOrigin: true },
        "/": {
          target: apiTarget.replace(/^http/, "ws"),
          ws: true,
          changeOrigin: true,
          bypass: (req) =>
            req.headers.upgrade === "websocket" ? undefined : req.url,
        },
      },
    },
    test: {
      environment: "happy-dom",
      globals: true,
      setupFiles: ["./src/tests/setup.ts"],
    },
  };
});
