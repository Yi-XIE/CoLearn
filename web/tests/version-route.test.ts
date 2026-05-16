import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";

test("version route defaults to the CoLearn releases repository", async () => {
  const source = readFileSync(
    path.resolve(process.cwd(), "app/api/version/route.ts"),
    "utf8",
  );

  assert.match(source, /YiVal\/CoLearn/);
  assert.doesNotMatch(source, /HKUDS\/DeepTutor/);
});
