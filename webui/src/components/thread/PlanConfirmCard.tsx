import { useState } from "react";
import { Check, Pencil, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface PlanNode {
  id?: string;
  label?: string;
  status?: string;
  summary?: string;
}

interface PlanConfirmCardProps {
  goal: string;
  nodes: PlanNode[];
  onConfirm: (nodes: PlanNode[]) => void;
  onDismiss: () => void;
}

export function PlanConfirmCard({ goal, nodes, onConfirm, onDismiss }: PlanConfirmCardProps) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");
  const [localNodes, setLocalNodes] = useState<PlanNode[]>(nodes);

  const handleEditStart = (index: number) => {
    setEditingIndex(index);
    setEditValue(localNodes[index].label || "");
  };

  const handleEditSave = () => {
    if (editingIndex === null) return;
    const updated = [...localNodes];
    updated[editingIndex] = { ...updated[editingIndex], label: editValue.trim() || updated[editingIndex].label };
    setLocalNodes(updated);
    setEditingIndex(null);
    setEditValue("");
  };

  const handleRemove = (index: number) => {
    setLocalNodes(localNodes.filter((_, i) => i !== index));
  };

  return (
    <div className={cn(
      "my-3 rounded-2xl border border-blue-200/60 bg-blue-50/30 p-4",
      "dark:border-blue-800/40 dark:bg-blue-950/20",
    )}>
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-sm font-semibold text-foreground">学习计划</h4>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-lg p-1 text-muted-foreground hover:bg-muted/50"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {goal && (
        <p className="mb-3 text-xs text-muted-foreground">
          目标：{goal}
        </p>
      )}

      {/* Plan nodes list */}
      <div className="space-y-1.5">
        {localNodes.map((node, index) => (
          <div
            key={node.id || index}
            className={cn(
              "group flex items-center gap-2 rounded-lg px-2.5 py-2",
              "border border-transparent hover:border-border/40 hover:bg-background/60",
            )}
          >
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border/60 text-xs font-medium text-muted-foreground">
              {index + 1}
            </span>

            {editingIndex === index ? (
              <div className="flex flex-1 items-center gap-1.5">
                <input
                  type="text"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleEditSave(); if (e.key === "Escape") setEditingIndex(null); }}
                  className="flex-1 rounded-md border border-border/60 bg-transparent px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-300"
                  autoFocus
                />
                <button type="button" onClick={handleEditSave} className="rounded p-0.5 text-green-600 hover:bg-green-50">
                  <Check className="h-3.5 w-3.5" />
                </button>
              </div>
            ) : (
              <>
                <span className="flex-1 text-sm text-foreground/90">{node.label}</span>
                <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                  <button type="button" onClick={() => handleEditStart(index)} className="rounded p-1 text-muted-foreground hover:text-foreground">
                    <Pencil className="h-3 w-3" />
                  </button>
                  <button type="button" onClick={() => handleRemove(index)} className="rounded p-1 text-muted-foreground hover:text-red-500">
                    <X className="h-3 w-3" />
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>

      {/* Action buttons */}
      <div className="mt-4 flex items-center gap-2">
        <button
          type="button"
          onClick={() => onConfirm(localNodes)}
          className={cn(
            "flex-1 rounded-xl bg-blue-500 px-4 py-2 text-sm font-medium text-white",
            "transition-colors hover:bg-blue-600",
          )}
        >
          确认计划，开始学习
        </button>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-xl border border-border/60 px-3 py-2 text-sm text-muted-foreground hover:bg-muted/40"
        >
          跳过
        </button>
      </div>
    </div>
  );
}
