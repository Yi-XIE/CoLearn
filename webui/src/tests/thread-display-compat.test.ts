import { describe, expect, it } from "vitest";

import { projectThreadMessages } from "@/lib/thread-display";
import type { UIMessage } from "@/lib/types";

describe("projectThreadMessages", () => {
  it("maps long_task rows to trace lines", () => {
    const legacy = {
      id: "x",
      role: "assistant",
      kind: "long_task",
      content: "long_task · done",
      createdAt: 1,
    } as unknown as UIMessage;
    const out = projectThreadMessages([legacy]);
    expect(out[0]!.kind).toBe("trace");
    expect(out[0]!.role).toBe("tool");
    expect(out[0]!.traces).toEqual(["long_task · done"]);
  });
});
