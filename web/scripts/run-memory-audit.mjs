import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import http from "node:http";
import path from "node:path";

const webRoot = path.resolve(process.cwd());
const port = Number(process.env.MEMORY_AUDIT_PORT || "3004");
const baseUrl = `http://127.0.0.1:${port}`;

function waitForServer(url, timeoutMs = 120000) {
  const startedAt = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      const req = http.get(url, (res) => {
        res.resume();
        if (res.statusCode && res.statusCode < 500) {
          resolve(true);
          return;
        }
        retry();
      });
      req.on("error", retry);
    };

    const retry = async () => {
      if (Date.now() - startedAt > timeoutMs) {
        reject(new Error(`Timed out waiting for ${url}`));
        return;
      }
      await delay(1000);
      check();
    };

    check();
  });
}

const server = spawn(
  process.execPath,
  ["./node_modules/next/dist/bin/next", "dev", "--hostname", "127.0.0.1", "--port", String(port)],
  {
    cwd: webRoot,
    stdio: "inherit",
    env: {
      ...process.env,
      NEXT_PUBLIC_API_BASE: baseUrl,
      NEXT_PUBLIC_AUTH_ENABLED: "false",
    },
  },
);

const cleanup = () => {
  if (!server.killed) {
    server.kill("SIGTERM");
  }
};

process.on("SIGINT", cleanup);
process.on("SIGTERM", cleanup);
process.on("exit", cleanup);

try {
  await waitForServer(`${baseUrl}/memory`);
  await new Promise((resolve, reject) => {
    const runner = spawn(
      process.execPath,
      [
        "./node_modules/playwright/cli.js",
        "test",
        "--project=ui-audit",
        "tests/e2e/memory-section.audit.ts",
        "tests/e2e/memory-sidebar-entry.audit.ts",
        "tests/e2e/memory-home-cta-loop.audit.ts",
      ],
      {
        cwd: webRoot,
        stdio: "inherit",
        env: {
          ...process.env,
          WEB_BASE_URL: baseUrl,
          NEXT_PUBLIC_API_BASE: baseUrl,
          NEXT_PUBLIC_AUTH_ENABLED: "false",
        },
      },
    );
    runner.on("exit", (code) => {
      if (code === 0) {
        resolve(true);
        return;
      }
      reject(new Error(`Playwright exited with code ${code}`));
    });
  });
} finally {
  cleanup();
}
