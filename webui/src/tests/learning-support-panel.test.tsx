import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LearningSupportPanel } from "@/components/thread/LearningSupportPanel";

describe("LearningSupportPanel", () => {
  it("renders prompt support references and retrieval misses", () => {
    render(
      <LearningSupportPanel
        support={{
          prompt_support_bundle: [
            {
              source_ref: "notes/force.md",
              chunk_id: "c1",
              support_type: "definition",
              summary: "力会改变物体运动状态。",
              target_type: "node",
              target_label: "牛顿第二定律",
            },
          ],
          retrieval_hits: [],
          retrieval_misses: [{ reason: "no_counterexample" }],
          retrieval_evidence_map: {},
          retrieval_query_context: { final_query: "牛顿第二定律 反例" },
          continuation_retrieval_hint: {
            retrieval_query_context: { final_query: "继续查受力分析步骤" },
          },
        }}
      />,
    );

    expect(screen.getByText("本轮依据")).toBeInTheDocument();
    expect(screen.getByText("力会改变物体运动状态。")).toBeInTheDocument();
    expect(screen.getByText("牛顿第二定律")).toBeInTheDocument();
    expect(screen.getByText(/资料缺口/)).toBeInTheDocument();
    expect(screen.getByText(/继续查受力分析步骤/)).toBeInTheDocument();
  });
});
