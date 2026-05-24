import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LearningSupportPanel } from "@/components/thread/LearningSupportPanel";

describe("LearningSupportPanel", () => {
  it("does not render when support is absent", () => {
    const { container } = render(<LearningSupportPanel support={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders references plus stacked notification cards", () => {
    render(
      <LearningSupportPanel
        support={{
          retrieval_active: true,
          turn_mode: "CHECK",
          learning_plan: {
            goal: "Newtonian mechanics",
            current_node_id: "node-force",
            plan_nodes: [{ id: "node-force", label: "Force and acceleration", status: "current" }],
            pending_checks: ["node-check"],
          },
          learning_board: {
            current_progress: "Force and acceleration",
            completed_nodes: ["node-motion"],
            blockers: ["Needs vector review"],
            objections: [],
            evidence_refs: ["notes/force.md"],
            continuation: "Continue with free-body diagrams",
          },
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
    expect(screen.getByText("CHECK")).toBeInTheDocument();
    expect(screen.getByText("Newtonian mechanics")).toBeInTheDocument();
    expect(screen.getByText("Force and acceleration")).toBeInTheDocument();
    expect(screen.getByText("力会改变物体运动状态。")).toBeInTheDocument();
    expect(screen.getByText("牛顿第二定律")).toBeInTheDocument();
    expect(screen.getByText("资料补证提醒")).toBeInTheDocument();
    expect(screen.getByText(/仍有 1 个资料缺口/)).toBeInTheDocument();
    expect(screen.getByText("下一轮计划")).toBeInTheDocument();
    expect(screen.getByText(/继续检索：继续查受力分析步骤/)).toBeInTheDocument();
  });

  it("renders learning board state without retrieval evidence", () => {
    render(
      <LearningSupportPanel
        support={{
          retrieval_active: false,
          turn_mode: "LEARN",
          learning_plan: {
            goal: "Energy conservation",
            current_node_id: "node-work",
            plan_nodes: [{ id: "node-work", label: "Work and energy", status: "current" }],
          },
          learning_board: {
            current_progress: "Work and energy",
            completed_nodes: [],
            blockers: [],
            objections: [],
            evidence_refs: [],
          },
          prompt_support_bundle: [],
          retrieval_hits: [],
          retrieval_misses: [],
          retrieval_evidence_map: {},
          retrieval_query_context: {},
          continuation_retrieval_hint: {},
        }}
      />,
    );

    expect(screen.getByText("LEARN")).toBeInTheDocument();
    expect(screen.getByText("Energy conservation")).toBeInTheDocument();
    expect(screen.getByText("Work and energy")).toBeInTheDocument();
    expect(screen.getByText("0 条资料")).toBeInTheDocument();
  });
});
