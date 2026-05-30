import "@testing-library/jest-dom/vitest";
import { beforeEach } from "vitest";

import i18n from "@/i18n";

const consoleWarn = console.warn.bind(console);
const consoleError = console.error.bind(console);
const ignoredWarningFragments = [
  "KaTeX doesn't work in quirks mode",
  "A suspended resource finished loading inside a test",
];

function shouldIgnoreTestWarning(args: unknown[]): boolean {
  return args.some(
    (arg) =>
      typeof arg === "string" &&
      ignoredWarningFragments.some((fragment) => arg.includes(fragment)),
  );
}

console.warn = (...args: unknown[]) => {
  if (shouldIgnoreTestWarning(args)) return;
  consoleWarn(...args);
};

console.error = (...args: unknown[]) => {
  if (shouldIgnoreTestWarning(args)) return;
  consoleError(...args);
};

// happy-dom doesn't ship with ``crypto.randomUUID``; shim a tiny v4-ish helper.
if (!("randomUUID" in globalThis.crypto)) {
  Object.defineProperty(globalThis.crypto, "randomUUID", {
    value: () =>
      "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
      }),
    configurable: true,
  });
}

// happy-dom in this setup doesn't expose a working Storage, so the app's
// window.localStorage calls throw. Install a minimal in-memory implementation
// shared by both the global and window bindings.
function installLocalStoragePolyfill(): void {
  const store = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => void store.delete(key),
    setItem: (key: string, value: string) => void store.set(key, String(value)),
  };
  for (const target of [globalThis, globalThis.window]) {
    if (!target) continue;
    Object.defineProperty(target, "localStorage", {
      value: storage,
      configurable: true,
      writable: true,
    });
  }
}

if (typeof globalThis.localStorage?.setItem !== "function") {
  installLocalStoragePolyfill();
}

beforeEach(async () => {
  await i18n.changeLanguage("en");
  document.documentElement.lang = "en";
  document.title = "CoLearn";
  window.localStorage.setItem("nanobot.locale", "en");
});
